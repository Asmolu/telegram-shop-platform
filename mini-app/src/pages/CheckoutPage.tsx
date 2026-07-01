import React from 'react';
import {
  checkoutCart,
  createIdempotencyKey,
  getApiErrorTelemetryCategory,
  getCart,
  getCustomerNotificationSubscription,
  getPersonalData,
  isTemporaryNetworkError,
  recordCustomerNotificationWriteAccess,
  toApiErrorMessage,
  validatePromoCode,
  type Cart,
  type CartItem,
  type CustomerNotificationSubscription,
  type OrderDeliveryMethod,
  type PersonalData,
  type PromoValidation,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, getSafeReturnTo, useRouter, withReturnTo } from '../shared/router/RouterProvider';
import { openTelegramLink, requestTelegramWriteAccess } from '../shared/telegram/webApp';
import { EmptyState, ErrorState, InlineNotice, PageLoader, TopBar } from '../shared/ui';
import { hashCorrelationKey, trackTelemetry } from '../shared/telemetry';
import { runLockedAction } from '../shared/utils/actionLock';
import { formatPrice, getDisplayOldPrice, getUserDisplayName } from '../shared/utils/format';
import { normalizeAssetUrl } from '../shared/utils/images';
import { getPromoErrorMessage, normalizePromoCode } from '../shared/utils/promo';
import { displaySize } from '../shared/utils/sizes';

const DELIVERY_METHODS: { value: OrderDeliveryMethod; label: string }[] = [
  { value: 'ROUTE_TAXI', label: 'Маршруткой' },
  { value: 'CITY_DELIVERY', label: 'Доставка по городу (Хасавюрт)' },
  { value: 'OZON', label: 'Озон доставка' },
  { value: 'WB', label: 'ВБ доставка' },
  { value: 'CDEK', label: 'СДЭК' },
];
const NOTIFICATION_WRITE_ACCESS_SOURCE = 'mini_app_request_write_access';
const BOT_1_NOTIFICATION_START_LINK = 'https://t.me/CheckYouStyleBot?start=notifications';

function areServiceNotificationsAvailable(subscription: CustomerNotificationSubscription | null) {
  if (!subscription) {
    return false;
  }
  if (typeof subscription.service_notifications_available === 'boolean') {
    return subscription.service_notifications_available;
  }
  return Boolean(subscription.has_chat && subscription.service_opt_in && !subscription.blocked_at);
}

function checkoutProductImageSrcSet(thumbnailUrl?: string | null, imageUrl?: string | null) {
  const normalizedThumbnail = normalizeAssetUrl(thumbnailUrl);
  const normalizedImage = normalizeAssetUrl(imageUrl);
  const entries: string[] = [];

  if (normalizedThumbnail) {
    entries.push(`${normalizedThumbnail} 240w`);
  }
  if (normalizedImage && normalizedImage !== normalizedThumbnail) {
    entries.push(`${normalizedImage} 480w`);
  }

  return entries.length > 1 ? entries.join(', ') : undefined;
}

export function CheckoutPage() {
  const { currentPath, searchParams, navigate } = useRouter();
  const { isAuthenticated, user, telegramUser } = useAuth();
  const returnToParam = searchParams.get('returnTo');
  const returnTo = getSafeReturnTo(returnToParam);
  const [cart, setCart] = React.useState<Cart | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [subscription, setSubscription] =
    React.useState<CustomerNotificationSubscription | null>(null);
  const [notificationPromptDismissed, setNotificationPromptDismissed] = React.useState(false);
  const [notificationPermissionLoading, setNotificationPermissionLoading] = React.useState(false);
  const [notificationPermissionMessage, setNotificationPermissionMessage] =
    React.useState<string | null>(null);
  const [notificationFallbackVisible, setNotificationFallbackVisible] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const checkoutKeyRef = React.useRef<string | null>(null);
  const checkoutLockRef = React.useRef(false);
  const initialPromoCode = React.useRef(searchParams.get('promo_code') ?? '');
  const [promoCode, setPromoCode] = React.useState(initialPromoCode.current);
  const [promoValidation, setPromoValidation] = React.useState<PromoValidation | null>(null);
  const [deliveryMethod, setDeliveryMethod] = React.useState<OrderDeliveryMethod>('CDEK');
  const [deliveryMethodError, setDeliveryMethodError] = React.useState<string | null>(null);
  const [form, setForm] = React.useState({
    contactName: getUserDisplayName(user ?? telegramUser),
    phone: user?.phone ?? '',
    city: '',
    height: '',
    weight: '',
    comment: '',
    username: telegramUser?.username ?? user?.username ?? '',
  });
  const editedFields = React.useRef(new Set<keyof typeof form>());

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!isAuthenticated) {
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const [result, personalData, notificationState] = await Promise.all([
          getCart(),
          getPersonalData().catch(() => null),
          getCustomerNotificationSubscription().catch(() => null),
        ]);
        if (!cancelled) {
          setCart(result);
          setSubscription(notificationState);
          if (personalData) {
            applyPersonalData(personalData);
          }
        }

        const code = normalizePromoCode(initialPromoCode.current);
        if (code && result.selected_distinct_item_count > 0) {
          try {
            const validation = await validatePromoCode(code);
            if (!cancelled) {
              setPromoValidation(validation);
              setPromoCode(validation.code);
            }
          } catch (promoError) {
            if (!cancelled) {
              setPromoValidation(null);
              setNotice(getPromoErrorMessage(promoError));
            }
          }
        }
      } catch (loadError) {
        if (!cancelled) setError(toApiErrorMessage(loadError));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    const retryLoad = () => void load();
    window.addEventListener('miniapp:network-retry', retryLoad);
    window.addEventListener('miniapp:network-restored', retryLoad);
    return () => {
      cancelled = true;
      window.removeEventListener('miniapp:network-retry', retryLoad);
      window.removeEventListener('miniapp:network-restored', retryLoad);
    };
  }, [isAuthenticated]);

  function updateField(field: keyof typeof form, value: string) {
    checkoutKeyRef.current = null;
    editedFields.current.add(field);
    setForm((current) => ({ ...current, [field]: value }));
  }

  function applyPersonalData(personalData: PersonalData) {
    const values: Partial<typeof form> = {
      contactName: personalData.recipient_name ?? undefined,
      phone: personalData.contact_phone ?? undefined,
      city: personalData.city ?? undefined,
      height: personalData.height_cm == null ? undefined : String(personalData.height_cm),
      weight: personalData.weight_kg == null ? undefined : String(personalData.weight_kg),
      comment: personalData.persistent_comment ?? undefined,
      username: personalData.telegram_username ?? undefined,
    };

    setForm((current) => {
      const next = { ...current };
      for (const [field, value] of Object.entries(values) as [keyof typeof form, string | undefined][]) {
        if (value !== undefined && !editedFields.current.has(field)) {
          next[field] = value;
        }
      }
      return next;
    });
  }

  async function applyPromo(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPromoValidation(null);
    if (!cart || cart.selected_distinct_item_count === 0) {
      setNotice('Выберите товары для оформления.');
      return;
    }
    const code = normalizePromoCode(promoCode);
    if (!code) {
      return;
    }

    try {
      const result = await validatePromoCode(code);
      setPromoValidation(result);
      setPromoCode(result.code);
      setNotice('Промокод применен.');
    } catch (promoError) {
      setNotice(getPromoErrorMessage(promoError));
    }
  }

  function updatePromoCode(value: string) {
    checkoutKeyRef.current = null;
    setPromoCode(value);
    if (!value.trim() || normalizePromoCode(value) !== promoValidation?.code) {
      setPromoValidation(null);
      setNotice(null);
    }
  }

  function clearPromo() {
    checkoutKeyRef.current = null;
    setPromoCode('');
    setPromoValidation(null);
    setNotice(null);
  }

  async function handleAllowOrderNotifications() {
    setNotificationPermissionLoading(true);
    setNotificationPermissionMessage(null);
    setNotificationFallbackVisible(false);

    try {
      const result = await requestTelegramWriteAccess();
      if (result === 'granted') {
        const nextState = await recordCustomerNotificationWriteAccess({
          granted: true,
          source: NOTIFICATION_WRITE_ACCESS_SOURCE,
        });
        setSubscription(nextState);
        if (areServiceNotificationsAvailable(nextState)) {
          setNotificationPermissionMessage('Уведомления о заказах включены');
          setNotificationPromptDismissed(true);
        } else {
          setNotificationPermissionMessage(
            nextState.availability_status === 'bot_blocked'
              ? 'Бот заблокирован. Откройте @CheckYouStyleBot и разблокируйте его.'
              : 'Откройте Bot 1, чтобы получать статусы заказа',
          );
          setNotificationFallbackVisible(true);
        }
        return;
      }

      if (result === 'denied') {
        const nextState = await recordCustomerNotificationWriteAccess({
          granted: false,
          source: NOTIFICATION_WRITE_ACCESS_SOURCE,
        }).catch(() => null);
        if (nextState) {
          setSubscription(nextState);
        }
        setNotificationPermissionMessage('Можно подключить уведомления через Bot 1');
      } else {
        setNotificationPermissionMessage('Откройте Bot 1, чтобы получать статусы заказа');
      }
      setNotificationFallbackVisible(true);
    } catch (permissionError) {
      setNotificationPermissionMessage(toApiErrorMessage(permissionError));
    } finally {
      setNotificationPermissionLoading(false);
    }
  }

  function handleOpenNotificationBot() {
    openTelegramLink(subscription?.bot_start_link ?? BOT_1_NOTIFICATION_START_LINK);
  }

  async function getValidatedPromoCodeForCheckout() {
    const code = normalizePromoCode(promoCode);
    if (!code) {
      return null;
    }

    if (promoValidation?.code === code) {
      return promoValidation.code;
    }

    const result = await validatePromoCode(code);
    setPromoValidation(result);
    setPromoCode(result.code);
    return result.code;
  }

  async function submitCheckout(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runLockedAction(checkoutLockRef, async () => {
      if (!cart || cart.selected_distinct_item_count === 0) {
        setNotice('Выберите товары для оформления.');
        return;
      }
      if (!form.contactName.trim() || !form.phone.trim() || !form.city.trim()) {
        setNotice('Заполните имя, телефон и город.');
        return;
      }
      if (!deliveryMethod) {
        setDeliveryMethodError('Выберите способ доставки.');
        setNotice('Выберите способ доставки.');
        return;
      }

      setBusy(true);
      try {
        let promoCodeForOrder: string | null = null;
        try {
          promoCodeForOrder = await getValidatedPromoCodeForCheckout();
        } catch (promoError) {
          setPromoValidation(null);
          setNotice(getPromoErrorMessage(promoError));
          return;
        }

        const deliveryComment = [
          form.height ? `Рост: ${form.height}` : '',
          form.weight ? `Вес: ${form.weight}` : '',
          form.username ? `Telegram: @${form.username.replace(/^@/, '')}` : '',
          form.comment,
        ].filter(Boolean).join('\n');

        if (!checkoutKeyRef.current) {
          checkoutKeyRef.current = createIdempotencyKey('checkout');
        }
        const currentCheckoutKey = checkoutKeyRef.current;

        trackTelemetry('checkout.started', {
          route: '/checkout',
          endpoint_scope: '/orders/checkout',
          method: 'POST',
        }, { priority: 'critical' });
        const order = await checkoutCart({
          contact_name: form.contactName.trim(),
          contact_phone: form.phone.trim(),
          delivery_method: deliveryMethod,
          delivery_address: form.city.trim(),
          delivery_comment: deliveryComment || null,
          promo_code: promoCodeForOrder,
        }, currentCheckoutKey);
        trackTelemetry('checkout.completed', {
          route: '/checkout',
          endpoint_scope: '/orders/checkout',
          method: 'POST',
          success: true,
          idempotency_key_hash: await hashCorrelationKey(currentCheckoutKey),
        }, { priority: 'critical' });
        checkoutKeyRef.current = null;
        window.dispatchEvent(new Event('miniapp:cart-updated'));
        navigate(withReturnTo(`/payment/${order.id}`, returnToParam), { replace: true });
      } catch (checkoutError) {
        const idempotencyHash = checkoutKeyRef.current
          ? await hashCorrelationKey(checkoutKeyRef.current)
          : undefined;
        const temporary = isTemporaryNetworkError(checkoutError);
        trackTelemetry(temporary ? 'checkout.ambiguous_outcome' : 'checkout.failed', {
          route: '/checkout',
          endpoint_scope: '/orders/checkout',
          method: 'POST',
          error_category: getApiErrorTelemetryCategory(checkoutError),
          success: false,
          idempotency_key_hash: idempotencyHash,
        }, { priority: 'critical' });
        if (!isTemporaryNetworkError(checkoutError)) {
          checkoutKeyRef.current = null;
        }
        setNotice(toApiErrorMessage(checkoutError));
      } finally {
        setBusy(false);
      }
    });
  }

  const selectedItems = cart?.items.filter((item) => item.is_selected) ?? [];
  const selectedTotal = cart?.selected_total ?? cart?.total ?? '0';
  const serviceNotificationsAvailable = areServiceNotificationsAvailable(subscription);
  const notificationAvailabilityStatus = subscription?.availability_status;
  const showNotificationPrompt = Boolean(
    subscription
    && !serviceNotificationsAvailable
    && !notificationPromptDismissed
    && notificationAvailabilityStatus !== 'service_opt_out',
  );
  const notificationFallbackLink = subscription?.bot_start_link ?? BOT_1_NOTIFICATION_START_LINK;

  if (!isAuthenticated) {
    return (
      <div className="page">
        <TopBar title="Оформление" backFallback={withReturnTo('/cart?tab=cart', returnToParam)} />
        <EmptyState
          title="Нужен вход через Telegram"
          message="Оформление заказа доступно после входа."
          actionLabel="Войти"
          onAction={() => navigate(getAuthPath(currentPath))}
        />
      </div>
    );
  }

  return (
    <div className="page">
      <TopBar title="Оформление" backFallback={withReturnTo('/cart?tab=cart', returnToParam)} />
      {loading ? <PageLoader text="Проверяем корзину..." /> : null}
      {!loading && error ? <ErrorState message={error} /> : null}
      {!loading && !error && (!cart || cart.items.length === 0) ? (
        <EmptyState title="Корзина пустая" actionLabel="Вернуться к покупкам" onAction={() => navigate(returnTo)} />
      ) : null}
      {!loading && !error && cart && cart.items.length > 0 && selectedItems.length === 0 ? (
        <EmptyState title="Нет выбранных товаров" actionLabel="Вернуться в корзину" onAction={() => navigate(withReturnTo('/cart?tab=cart', returnToParam))} />
      ) : null}
      {!loading && !error && cart && selectedItems.length > 0 ? (
        <>
          {notice ? (
            <InlineNotice tone={notice.includes('применен') ? 'success' : 'warning'}>
              <span>{notice}</span>
              <button type="button" onClick={() => setNotice(null)}>×</button>
            </InlineNotice>
          ) : null}

          <section className="summary-card checkout-summary-card">
            <h2>Корзина</h2>
            <div className="checkout-item-list">
              {selectedItems.map((item) => (
                <CheckoutItemSummary item={item} key={item.id} />
              ))}
            </div>
            <div><span>Выбрано</span><strong>{cart.selected_quantity_total}</strong></div>
            <div><span>Товары</span><strong>{formatPrice(selectedTotal)}</strong></div>
            <div><span>Скидка</span><strong>{formatPrice(promoValidation?.discount_amount ?? 0)}</strong></div>
            <div className="summary-card__total"><span>Итого</span><strong>{formatPrice(promoValidation?.total_amount ?? selectedTotal)}</strong></div>
          </section>

          <form className="promo-form" onSubmit={applyPromo}>
            <input value={promoCode} onChange={(event) => updatePromoCode(event.target.value)} placeholder="Введите промокод" />
            <button className="secondary-button" type="submit" disabled={!promoCode.trim()}>Применить</button>
          </form>
          {promoValidation ? (
            <div className="promo-status promo-status--success">
              <span>{promoValidation.code}: −{formatPrice(promoValidation.discount_amount)}</span>
              <button type="button" onClick={clearPromo}>Убрать</button>
            </div>
          ) : null}

          {showNotificationPrompt ? (
            <section className="notification-permission-prompt">
              <div>
                <h2>Разрешить уведомления о заказе в Telegram?</h2>
                <p>Мы сможем прислать статус заказа: принят, в пути, доставлен.</p>
                {subscription?.availability_status === 'bot_blocked' ? (
                  <p className="form-error">
                    Бот заблокирован. Откройте @CheckYouStyleBot и разблокируйте его.
                  </p>
                ) : null}
                {notificationPermissionMessage ? (
                  <p className="muted-text">{notificationPermissionMessage}</p>
                ) : null}
                {notificationFallbackVisible ? (
                  <button
                    className="secondary-button full-width"
                    type="button"
                    onClick={handleOpenNotificationBot}
                  >
                    Открыть Bot 1
                  </button>
                ) : null}
              </div>
              <div className="notification-permission-prompt__actions">
                <button
                  className="primary-button"
                  disabled={notificationPermissionLoading}
                  type="button"
                  onClick={handleAllowOrderNotifications}
                >
                  {notificationPermissionLoading ? 'Запрашиваем...' : 'Разрешить уведомления'}
                </button>
                <button
                  className="text-button"
                  disabled={notificationPermissionLoading}
                  type="button"
                  onClick={() => setNotificationPromptDismissed(true)}
                >
                  Позже
                </button>
              </div>
              {notificationFallbackVisible ? (
                <a className="notification-permission-prompt__fallback" href={notificationFallbackLink}>
                  {notificationFallbackLink}
                </a>
              ) : null}
            </section>
          ) : null}

          <form className="checkout-form" onSubmit={submitCheckout}>
            <label>Получатель<input value={form.contactName} onChange={(event) => updateField('contactName', event.target.value)} required /></label>
            <label>Телефон<input value={form.phone} onChange={(event) => updateField('phone', event.target.value)} required inputMode="tel" /></label>
            <label>Город<input value={form.city} onChange={(event) => updateField('city', event.target.value)} required /></label>
            <label
              className="delivery-method-field"
              aria-invalid={deliveryMethodError ? 'true' : undefined}
              aria-describedby={deliveryMethodError ? 'delivery-method-error' : undefined}
            >
              <span>Способ доставки</span>
              <span className="delivery-method-select">
                <select
                  name="delivery-method"
                  value={deliveryMethod}
                  onChange={(event) => {
                    checkoutKeyRef.current = null;
                    setDeliveryMethod(event.target.value as OrderDeliveryMethod);
                    setDeliveryMethodError(null);
                    setNotice(null);
                  }}
                >
                  {DELIVERY_METHODS.map((method) => (
                    <option value={method.value} key={method.value}>
                      {method.label}
                    </option>
                  ))}
                </select>
              </span>
              {deliveryMethodError ? (
                <p className="form-error" id="delivery-method-error">{deliveryMethodError}</p>
              ) : null}
            </label>
            <div className="two-inputs">
              <label>Рост<input value={form.height} onChange={(event) => updateField('height', event.target.value)} inputMode="numeric" /></label>
              <label>Вес<input value={form.weight} onChange={(event) => updateField('weight', event.target.value)} inputMode="numeric" /></label>
            </div>
            <label>Имя в Telegram<input value={form.username} onChange={(event) => updateField('username', event.target.value)} /></label>
            <label>Комментарий<textarea value={form.comment} onChange={(event) => updateField('comment', event.target.value)} rows={3} /></label>
            {serviceNotificationsAvailable ? (
              <InlineNotice tone="success">
                <span>Уведомления о заказах включены</span>
              </InlineNotice>
            ) : null}
            <button className="primary-button" type="submit" disabled={busy}>
              {busy ? 'Создаём заказ...' : 'Оформить заказ'}
            </button>
          </form>
        </>
      ) : null}
    </div>
  );
}

function CheckoutItemSummary({ item }: { item: CartItem }) {
  const imageUrl = normalizeAssetUrl(item.product.thumbnail_image_url ?? item.product.image_url);
  const brand = item.product.brand?.trim();
  const color = item.product_variant.color?.trim();
  const size = displaySize(item.product.size_grid, item.product_variant.size, true);
  const sku = item.product_variant.sku?.trim();
  const quantity = item.quantity;
  const oldPrice = getDisplayOldPrice(
    item.unit_price,
    item.product.old_price,
    item.product.compare_at_price,
  );
  const detailParts = [
    size,
    color ?? '',
    sku ? `арт. ${sku}` : '',
  ].filter(Boolean);

  return (
    <article className="checkout-item-card">
      <span className="checkout-item-card__image">
        {imageUrl ? (
          <img
            src={imageUrl}
            srcSet={checkoutProductImageSrcSet(item.product.thumbnail_image_url, item.product.image_url)}
            sizes="96px"
            alt=""
            width={96}
            height={96}
            loading="lazy"
            decoding="async"
          />
        ) : (
          <span>{item.product.name.slice(0, 1)}</span>
        )}
      </span>
      <div className="checkout-item-card__content">
        <div className="checkout-item-card__price-row">
          <strong>{formatPrice(item.unit_price)}</strong>
          {oldPrice ? <del>{formatPrice(oldPrice)}</del> : null}
        </div>
        {brand ? <span className="checkout-item-card__brand">{brand}</span> : null}
        <strong className="checkout-item-card__title">{item.product.name}</strong>
        {detailParts.length > 0 ? (
          <p className="checkout-item-card__meta">{detailParts.join(' · ')}</p>
        ) : null}
        <p className="checkout-item-card__quantity">
          <span>Кол-во: {quantity}</span>
          {quantity > 1 ? <span>Сумма: {formatPrice(item.subtotal)}</span> : null}
        </p>
      </div>
    </article>
  );
}
