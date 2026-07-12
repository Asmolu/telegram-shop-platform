import React from 'react';
import { useRouter } from '../shared/router/RouterProvider';
import { SellerContactCard, TopBar } from '../shared/ui';

const faqItems = [
  {
    id: 'order',
    question: 'Как совершить заказ?',
    answer: 'Выберите товар, затем размер или цвет, добавьте его в корзину, примените промокод при наличии и оформите заказ. После этого дождитесь подтверждения продавца и следите за статусом во вкладке «Заказы».',
  },
  {
    id: 'promo',
    question: 'Как применить промокод?',
    answer: 'Введите промокод в корзине или на странице оформления. Итог пересчитается автоматически.',
  },
  {
    id: 'status',
    question: 'Как узнать статус заказа?',
    answer: 'Откройте «Покупки» и вкладку «Заказы». Статус обновляется продавцом.',
  },
  {
    id: 'size',
    question: 'Как подобрать размер?',
    answer: 'На странице товара доступны размеры и остатки. Рост и вес можно оставить в комментарии к заказу.',
  },
  {
    id: 'contact',
    question: 'Как связаться с продавцом?',
    answer: 'Используйте кнопку Telegram ниже или раздел поддержки в профиле.',
  },
  {
    id: 'review',
    question: 'Как оставить отзыв?',
    answer: 'Откройте товар после покупки, поставьте оценку и отправьте отзыв. Он появится после модерации.',
  },
  {
    id: 'return',
    question: 'Как совершить возврат товара?',
    answer: (
      <div className="faq-answer">
        <p>Возврат можно оформить в течение 24 часов с момента, когда заказ получил статус «Доставлено», если товар не был в употреблении и сохранены его товарный вид, потребительские свойства, комплектность и фабричные ярлыки.</p>
        <p>Чтобы оформить возврат, откройте:</p>
        <p className="faq-answer__path">«Покупки» → вкладка «Заказы» → «Оформить возврат» под нужным заказом.</p>
        <p>Выберите товары, которые хотите вернуть, обязательно укажите причину и приложите хотя бы одно фото или видео. Материалы должны позволять продавцу увидеть состояние товара и причину обращения.</p>
        <p>Возврат доступен только для доставленных заказов и товаров, разрешённых к возврату. Статус заявки можно посмотреть в информации о заказе. Стоимость доставки не возвращается. Продавец вправе отказать в возврате без объяснения причин.</p>
      </div>
    ),
  },
];

export function FaqPage() {
  const { searchParams } = useRouter();
  const topic = searchParams.get('topic');
  const initialOpenIndex = Math.max(0, faqItems.findIndex((item) => item.id === topic));
  const [openIndex, setOpenIndex] = React.useState(initialOpenIndex);
  const [contactsOpen, setContactsOpen] = React.useState(false);

  React.useEffect(() => {
    const nextIndex = faqItems.findIndex((item) => item.id === topic);
    if (nextIndex >= 0) {
      setOpenIndex(nextIndex);
    }
  }, [topic]);

  return (
    <div className="page page--faq">
      <TopBar title="FAQ" backFallback="/main" />
      <div className="accordion-list">
        {faqItems.map((item, index) => (
          <section className="accordion-item" key={item.id}>
            <button type="button" onClick={() => setOpenIndex(openIndex === index ? -1 : index)}>
              <span>{item.question}</span>
              <strong>{openIndex === index ? '−' : '+'}</strong>
            </button>
            {openIndex === index ? (
              <div className="accordion-item__answer">{item.answer}</div>
            ) : null}
          </section>
        ))}
      </div>
      <button
        className="primary-button full-width faq-contact-button"
        type="button"
        aria-expanded={contactsOpen}
        onClick={() => setContactsOpen((current) => !current)}
      >
        Связаться с продавцом
      </button>
      {contactsOpen ? <SellerContactCard className="faq-contact-card" /> : null}
    </div>
  );
}
