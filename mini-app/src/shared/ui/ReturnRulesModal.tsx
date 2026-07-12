import React from 'react';

type ReturnRulesModalProps = {
  onCancel: () => void;
  onContinue: () => void;
  returnFocusTo: HTMLElement | null;
};

const rules = [
  'Возврат можно оформить в течение 24 часов с момента, когда заказ получил статус «Доставлено».',
  'Возврат доступен только для товаров, разрешённых к возврату.',
  'Товар не должен быть в употреблении. Должны быть сохранены товарный вид, потребительские свойства, комплектность и фабричные ярлыки.',
  'Для оформления возврата необходимо выбрать товары, указать причину и приложить хотя бы одно фото или видео.',
  'Стоимость доставки не возвращается.',
  'Продавец вправе отказать в возврате без объяснения причин.',
];

export function ReturnRulesModal({ onCancel, onContinue, returnFocusTo }: ReturnRulesModalProps) {
  const [consented, setConsented] = React.useState(false);
  const cancelRef = React.useRef<HTMLButtonElement>(null);
  const titleId = React.useId();

  React.useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    cancelRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onCancel();
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      returnFocusTo?.focus();
    };
  }, [onCancel, returnFocusTo]);

  return (
    <div
      className="return-rules-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <section
        aria-labelledby={titleId}
        aria-modal="true"
        className="return-rules-modal"
        role="dialog"
      >
        <h2 id={titleId}>Правила возврата</h2>
        <ol className="return-rules-list">
          {rules.map((rule) => <li key={rule}>{rule}</li>)}
        </ol>
        <label className="return-rules-consent">
          <input
            checked={consented}
            type="checkbox"
            onChange={(event) => setConsented(event.target.checked)}
          />
          <span>Я ознакомился(ась) и согласен(на) с Правилами возврата.</span>
        </label>
        <div className="return-rules-actions">
          <button className="secondary-button" ref={cancelRef} type="button" onClick={onCancel}>
            Отмена
          </button>
          <button
            className="primary-button"
            disabled={!consented}
            type="button"
            onClick={onContinue}
          >
            Продолжить оформление
          </button>
        </div>
      </section>
    </div>
  );
}
