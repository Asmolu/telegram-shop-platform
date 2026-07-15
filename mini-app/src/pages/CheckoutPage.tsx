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
import {
  EmptyState,
  ErrorState,
  InlineNotice,
  LookSourceHeader,
  PageLoader,
  PromoToast,
  TopBar,
  promoToastFromMessage,
  type PromoToastState,
} from '../shared/ui';
import { hashCorrelationKey, trackTelemetry } from '../shared/telemetry';
import { runLockedAction } from '../shared/utils/actionLock';
import { formatPrice, getDisplayOldPrice, getUserDisplayName } from '../shared/utils/format';
import { normalizeAssetUrl } from '../shared/utils/images';
import { getPromoErrorMessage, normalizePromoCode } from '../shared/utils/promo';
import { displaySize } from '../shared/utils/sizes';
import { groupLookSourcedItems } from '../shared/utils/sourceGroups';
import { getMotionAwareScrollBehavior } from '../shared/utils/motion';
import { checkoutFieldOrder, mapCheckoutApiValidationErrors, validateCheckoutForm, type CheckoutField, type CheckoutFieldErrors } from './checkoutValidation';

const DELIVERY_METHODS: { value: OrderDeliveryMethod; label: string; price: number }[] = [
  { value: 'ROUTE_TAXI', label: 'Маршруткой', price: 200 },
  { value: 'CITY_DELIVERY', label: 'Доставка по городу', price: 300 },
  { value: 'OZON', label: 'Озон доставка', price: 200 },
  { value: 'WB', label: 'ВБ доставка', price: 0 },
  { value: 'CDEK', label: 'СДЭК', price: 0 },
  { value: 'PICKUP', label: 'Самовывоз', price: 0 },
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

function cartItemsSubtotal(items: CartItem[]) {
  return items.reduce((total, item) => total + Number(item.subtotal), 0);
}

function deliveryPriceFor(method: OrderDeliveryMethod) {
  return DELIVERY_METHODS.find((item) => item.value === method)?.price ?? 0;
}

function formatDeliveryPriceLabel(method: { value: OrderDeliveryMethod; price: number }) {
  if (method.value === 'PICKUP') {
    return 'Бесплатно';
  }
  if (method.value === 'WB' || method.value === 'CDEK') {
    return 'Нужно уточнить';
  }
  return `+${formatPrice(method.price)}`;
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
  const [promoToast, setPromoToast] = React.useState<PromoToastState | null>(null);
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
  const [deliverySelectorOpen, setDeliverySelectorOpen] = React.useState(false);
  const [fieldErrors, setFieldErrors] = React.useState<CheckoutFieldErrors>({});
  const fieldRefs = React.useRef<Partial<Record<CheckoutField, HTMLElement | null>>>({});
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
              const message = getPromoErrorMessage(promoError);
              const toast = promoToastFromMessage(message);
              showPromoToast(toast.text, toast.tone);
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
    if (field in fieldErrors) setFieldErrors((current) => ({ ...current, [field]: undefined }));
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
      showPromoToast('Успешно!', 'success');
    } catch (promoError) {
      const message = getPromoErrorMessage(promoError);
      const toast = promoToastFromMessage(message);
      showPromoToast(toast.text, toast.tone);
    }
  }

  function showPromoToast(text: string, tone: PromoToastState['tone']) {
    setPromoToast({ id: Date.now(), text, tone });
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

  function selectDeliveryMethod(method: OrderDeliveryMethod) {
    checkoutKeyRef.current = null;
    setDeliveryMethod(method);
    setFieldErrors((current) => ({ ...current, deliveryMethod: undefined }));
    setDeliverySelectorOpen(false);
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
      const errors = validateCheckoutForm({
        contactName: form.contactName, phone: form.phone, deliveryMethod,
        city: form.city, height: form.height, weight: form.weight,
      });
      const firstError = checkoutFieldOrder.find((field) => errors[field]);
      if (firstError) {
        setFieldErrors(errors);
        setNotice('Проверьте обязательные поля.');
        focusCheckoutField(firstError);
        return;
      }
      setFieldErrors({});

      setBusy(true);
      try {
        let promoCodeForOrder: string | null = null;
        try {
          promoCodeForOrder = await getValidatedPromoCodeForCheckout();
        } catch (promoError) {
          setPromoValidation(null);
          const message = getPromoErrorMessage(promoError);
          const toast = promoToastFromMessage(message);
          showPromoToast(toast.text, toast.tone);
          return;
        }

        if (!checkoutKeyRef.current) {
          checkoutKeyRef.current = createIdempotencyKey('checkout');
        }
        const currentCheckoutKey = checkoutKeyRef.current;

        trackTelemetry('checkout.started', {
          route: '/checkout',
          endpoint_scope: '/orders/checkout',
          method: 'POST',
        }, { priority: 'critical' });
        const height = form.height.trim();
        const weight = form.weight.trim().replace(',', '.');
        const order = await checkoutCart({
          contact_name: form.contactName.trim(),
          contact_phone: form.phone.trim(),
          delivery_method: deliveryMethod,
          delivery_address: form.city.trim(),
          delivery_comment: null,
          ...(height ? { height_cm: Number.parseInt(height, 10) } : {}),
          ...(weight ? { weight_kg: Number(weight) } : {}),
          telegram_username: form.username.trim() || null,
          customer_comment: form.comment.trim() || null,
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
        const serverErrors = mapCheckoutApiValidationErrors(checkoutError);
        if (serverErrors) {
          const firstError = checkoutFieldOrder.find((field) => serverErrors[field]);
          setFieldErrors(serverErrors);
          setNotice(firstError ? 'Проверьте обязательные поля.' : 'Проверьте данные и попробуйте снова.');
          if (firstError) focusCheckoutField(firstError);
          return;
        }
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

  function focusCheckoutField(field: CheckoutField) {
    requestAnimationFrame(() => {
      const element = fieldRefs.current[field];
      if (typeof element?.scrollIntoView === 'function') {
        element.scrollIntoView({ block: 'center', behavior: getMotionAwareScrollBehavior() });
      }
      element?.focus({ preventScroll: true });
    });
  }

  const selectedItems = cart?.items.filter((item) => item.is_selected) ?? [];
  const selectedTotal = cart?.selected_total ?? cart?.total ?? '0';
  const selectedDeliveryMethod = DELIVERY_METHODS.find((method) => method.value === deliveryMethod) ?? DELIVERY_METHODS[0];
  const deliveryPrice = deliveryPriceFor(deliveryMethod);
  const goodsTotalAfterDiscount = Number(promoValidation?.total_amount ?? selectedTotal);
  const finalTotal = goodsTotalAfterDiscount + deliveryPrice;
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
          <PromoToast toast={promoToast} onDismiss={() => setPromoToast(null)} />

          <section className="summary-card checkout-summary-card">
            <h2>Корзина</h2>
            <div className="checkout-item-list">
              {groupLookSourcedItems(selectedItems).map((section) => (
                section.kind === 'look' ? (
                  <React.Fragment key={section.key}>
                    <LookSourceHeader
                      imageUrl={section.imageUrl}
                      subtotal={cartItemsSubtotal(section.items)}
                      title={section.title}
                    />
                    {section.items.map((item) => (
                      <CheckoutItemSummary item={item} key={item.id} />
                    ))}
                  </React.Fragment>
                ) : (
                  <CheckoutItemSummary item={section.item} key={section.key} />
                )
              ))}
            </div>
            <div><span>Выбрано</span><strong>{cart.selected_quantity_total}</strong></div>
            <div><span>Товары</span><strong>{formatPrice(selectedTotal)}</strong></div>
            <div><span>Скидка</span><strong>{formatPrice(promoValidation?.discount_amount ?? 0)}</strong></div>
            <div><span>Доставка</span><strong>{formatPrice(deliveryPrice)}</strong></div>
            <div className="summary-card__total"><span>Итого</span><strong>{formatPrice(finalTotal)}</strong></div>
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

          <form className="checkout-form" onSubmit={submitCheckout} noValidate>
            <p className="checkout-field-legend"><FieldMarker required /> — обязательное поле. Поля без отметки — необязательные.</p>
            <CheckoutTextField field="contactName" label="Получатель" value={form.contactName} error={fieldErrors.contactName} elementRef={(node) => { fieldRefs.current.contactName = node; }} onChange={(value) => updateField('contactName', value)} />
            <CheckoutTextField field="phone" label="Телефон" value={form.phone} error={fieldErrors.phone} elementRef={(node) => { fieldRefs.current.phone = node; }} onChange={(value) => updateField('phone', value)} inputMode="tel" />
            <div
              className="delivery-method-field"
              aria-invalid={fieldErrors.deliveryMethod ? 'true' : undefined}
            >
              <span>Способ доставки<FieldMarker required /></span>
              <button
                aria-controls="delivery-method-options"
                aria-expanded={deliverySelectorOpen}
                className="delivery-method-trigger"
                aria-invalid={Boolean(fieldErrors.deliveryMethod)}
                aria-required="true"
                aria-describedby={fieldErrors.deliveryMethod ? 'checkout-deliveryMethod-error' : undefined}
                ref={(node) => { fieldRefs.current.deliveryMethod = node; }}
                type="button"
                onClick={() => setDeliverySelectorOpen((current) => !current)}
              >
                <span>{selectedDeliveryMethod.label}</span>
                <span className="delivery-method-option__meta">
                  <strong>{formatDeliveryPriceLabel(selectedDeliveryMethod)}</strong>
                  <span className="delivery-method-chevron" aria-hidden="true">⌄</span>
                </span>
              </button>
              {deliverySelectorOpen ? (
                <span className="delivery-method-options" id="delivery-method-options" role="radiogroup">
                  {DELIVERY_METHODS.map((method) => (
                    <button
                      aria-checked={deliveryMethod === method.value}
                      className="delivery-method-option"
                      key={method.value}
                      role="radio"
                      type="button"
                      onClick={() => selectDeliveryMethod(method.value)}
                    >
                      <span>{method.label}</span>
                      <strong>{formatDeliveryPriceLabel(method)}</strong>
                    </button>
                  ))}
                </span>
              ) : null}
              {fieldErrors.deliveryMethod ? (
                <p className="checkout-field-error" id="checkout-deliveryMethod-error">{fieldErrors.deliveryMethod}</p>
              ) : null}
            </div>
            <CheckoutTextField field="city" label="Адрес (город, улица, номер дома)" value={form.city} error={fieldErrors.city} elementRef={(node) => { fieldRefs.current.city = node; }} onChange={(value) => updateField('city', value)} />
            <p className="checkout-size-hint">
              Если хотите, укажите рост и вес — мы подберём размер по вашим параметрам.
            </p>
            <div className="two-inputs">
              <CheckoutTextField field="height" label="Рост" value={form.height} error={fieldErrors.height} elementRef={(node) => { fieldRefs.current.height = node; }} onChange={(value) => updateField('height', value)} inputMode="numeric" required={false} />
              <CheckoutTextField field="weight" label="Вес" value={form.weight} error={fieldErrors.weight} elementRef={(node) => { fieldRefs.current.weight = node; }} onChange={(value) => updateField('weight', value)} inputMode="decimal" required={false} />
            </div>
            <label><span>Имя в Telegram<FieldMarker required={false} /></span><input aria-label="Имя в Telegram" value={form.username} onChange={(event) => updateField('username', event.target.value)} /></label>
            <label><span>Комментарий<FieldMarker required={false} /></span><textarea aria-label="Комментарий" value={form.comment} onChange={(event) => updateField('comment', event.target.value)} rows={3} /></label>
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

function FieldMarker({ required }: { required: boolean }) {
  if (!required) return null;
  return <span className="checkout-field-marker checkout-field-marker--required" title="обязательное поле" aria-hidden="true">*</span>;
}

function CheckoutTextField({ field, label, value, error, onChange, elementRef, inputMode, required = true }: {
  field: CheckoutField; label: string; value: string; error?: string;
  onChange: (value: string) => void; elementRef: (node: HTMLInputElement | null) => void;
  inputMode?: React.HTMLAttributes<HTMLInputElement>['inputMode'];
  required?: boolean;
}) {
  const errorId = `checkout-${field}-error`;
  return (
    <label>
      <span>{label}<FieldMarker required={required} /></span>
      <input ref={elementRef} aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} inputMode={inputMode} aria-required={required} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined} />
      {error ? <span className="checkout-field-error" id={errorId}>{error}</span> : null}
    </label>
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
