import React from 'react';

export type PromoToastTone = 'error' | 'used' | 'success';

export type PromoToastState = {
  id: number;
  text: string;
  tone: PromoToastTone;
};

export function PromoToast({
  toast,
  onDismiss,
}: {
  toast: PromoToastState | null;
  onDismiss: () => void;
}) {
  React.useEffect(() => {
    if (!toast) {
      return undefined;
    }
    const timer = window.setTimeout(onDismiss, 3000);
    return () => window.clearTimeout(timer);
  }, [onDismiss, toast]);

  if (!toast) {
    return null;
  }

  return (
    <div className="promo-toast-slot" aria-live="polite">
      <div className={`promo-toast promo-toast--${toast.tone}`} key={toast.id}>
        {toast.text}
      </div>
    </div>
  );
}

export function promoToastFromMessage(message: string): Omit<PromoToastState, 'id'> {
  if (message === 'Вы уже использовали этот промокод.') {
    return { text: message, tone: 'used' };
  }
  if (message === 'Промокод не найден.') {
    return { text: message, tone: 'error' };
  }
  return { text: message, tone: 'error' };
}
