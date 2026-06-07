import React from 'react';
import { checkoutCart, getCart, toApiErrorMessage, validatePromoCode, type Cart, type PromoValidation } from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, getSafeReturnTo, useRouter, withReturnTo } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, PageLoader, TopBar } from '../shared/ui';
import { formatPrice, getUserDisplayName } from '../shared/utils/format';
import { getPromoErrorMessage, normalizePromoCode } from '../shared/utils/promo';

export function CheckoutPage() {
  const { currentPath, searchParams, navigate } = useRouter();
  const { isAuthenticated, user, telegramUser } = useAuth();
  const returnToParam = searchParams.get('returnTo');
  const returnTo = getSafeReturnTo(returnToParam);
  const [cart, setCart] = React.useState<Cart | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const initialPromoCode = React.useRef(searchParams.get('promo_code') ?? '');
  const [promoCode, setPromoCode] = React.useState(initialPromoCode.current);
  const [promoValidation, setPromoValidation] = React.useState<PromoValidation | null>(null);
  const [form, setForm] = React.useState({
    contactName: getUserDisplayName(user ?? telegramUser),
    phone: user?.phone ?? '',
    city: '',
    height: '',
    weight: '',
    comment: '',
    username: telegramUser?.username ?? user?.username ?? '',
  });

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
        const result = await getCart();
        if (!cancelled) {
          setCart(result);
        }

        const code = normalizePromoCode(initialPromoCode.current);
        if (code && result.items.length > 0) {
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
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  function updateField(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function applyPromo(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPromoValidation(null);
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
    setPromoCode(value);
    if (!value.trim() || normalizePromoCode(value) !== promoValidation?.code) {
      setPromoValidation(null);
      setNotice(null);
    }
  }

  function clearPromo() {
    setPromoCode('');
    setPromoValidation(null);
    setNotice(null);
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
    if (!form.contactName.trim() || !form.phone.trim() || !form.city.trim()) {
      setNotice('Заполните имя, телефон и город.');
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

      const order = await checkoutCart({
        contact_name: form.contactName.trim(),
        contact_phone: form.phone.trim(),
        delivery_address: form.city.trim(),
        delivery_comment: deliveryComment || null,
        promo_code: promoCodeForOrder,
      });
      window.dispatchEvent(new Event('miniapp:cart-updated'));
      navigate(withReturnTo(`/order-success/${order.id}`, returnToParam), { replace: true });
    } catch (checkoutError) {
      setNotice(toApiErrorMessage(checkoutError));
    } finally {
      setBusy(false);
    }
  }

  if (!isAuthenticated) {
    return (
      <div className="page">
        <TopBar title="Оформление" onBack={() => navigate(withReturnTo('/cart?tab=cart', returnToParam))} />
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
      <TopBar title="Оформление" onBack={() => navigate(withReturnTo('/cart?tab=cart', returnToParam))} />
      {loading ? <PageLoader text="Проверяем корзину..." /> : null}
      {!loading && error ? <ErrorState message={error} /> : null}
      {!loading && !error && (!cart || cart.items.length === 0) ? (
        <EmptyState title="Корзина пустая" actionLabel="Вернуться к покупкам" onAction={() => navigate(returnTo)} />
      ) : null}
      {!loading && !error && cart && cart.items.length > 0 ? (
        <>
          {notice ? (
            <InlineNotice tone={notice.includes('применен') ? 'success' : 'warning'}>
              <span>{notice}</span>
              <button type="button" onClick={() => setNotice(null)}>×</button>
            </InlineNotice>
          ) : null}

          <section className="summary-card">
            <h2>Корзина</h2>
            {cart.items.map((item) => (
              <div key={item.id}><span>{item.product.name} × {item.quantity}</span><strong>{formatPrice(item.subtotal)}</strong></div>
            ))}
            <div><span>Скидка</span><strong>{formatPrice(promoValidation?.discount_amount ?? 0)}</strong></div>
            <div className="summary-card__total"><span>Итого</span><strong>{formatPrice(promoValidation?.total_amount ?? cart.total)}</strong></div>
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

          <form className="checkout-form" onSubmit={submitCheckout}>
            <label>Получатель<input value={form.contactName} onChange={(event) => updateField('contactName', event.target.value)} required /></label>
            <label>Телефон<input value={form.phone} onChange={(event) => updateField('phone', event.target.value)} required inputMode="tel" /></label>
            <label>Город<input value={form.city} onChange={(event) => updateField('city', event.target.value)} required /></label>
            <div className="two-inputs">
              <label>Рост<input value={form.height} onChange={(event) => updateField('height', event.target.value)} inputMode="numeric" /></label>
              <label>Вес<input value={form.weight} onChange={(event) => updateField('weight', event.target.value)} inputMode="numeric" /></label>
            </div>
            <label>Имя в Telegram<input value={form.username} onChange={(event) => updateField('username', event.target.value)} /></label>
            <label>Комментарий<textarea value={form.comment} onChange={(event) => updateField('comment', event.target.value)} rows={3} /></label>
            <button className="primary-button" type="submit" disabled={busy}>
              {busy ? 'Создаём заказ...' : 'Оформить заказ'}
            </button>
          </form>
        </>
      ) : null}
    </div>
  );
}
