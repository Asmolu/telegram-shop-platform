import React from 'react';
import { useRouter } from '../shared/router/RouterProvider';
import { TopBar } from '../shared/ui';
import { getTelegramBotUrl } from '../shared/telegram/webApp';

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
];

export function FaqPage() {
  const { navigate, searchParams } = useRouter();
  const topic = searchParams.get('topic');
  const initialOpenIndex = Math.max(0, faqItems.findIndex((item) => item.id === topic));
  const [openIndex, setOpenIndex] = React.useState(initialOpenIndex);
  const botUrl = getTelegramBotUrl();

  React.useEffect(() => {
    const nextIndex = faqItems.findIndex((item) => item.id === topic);
    if (nextIndex >= 0) {
      setOpenIndex(nextIndex);
    }
  }, [topic]);

  return (
    <div className="page page--faq">
      <TopBar title="FAQ" onBack={() => navigate('/main')} />
      <div className="accordion-list">
        {faqItems.map((item, index) => (
          <section className="accordion-item" key={item.id}>
            <button type="button" onClick={() => setOpenIndex(openIndex === index ? -1 : index)}>
              <span>{item.question}</span>
              <strong>{openIndex === index ? '−' : '+'}</strong>
            </button>
            {openIndex === index ? <p>{item.answer}</p> : null}
          </section>
        ))}
      </div>
      {botUrl ? (
        <a className="primary-button full-width faq-contact-button" href={botUrl}>
          Связаться с продавцом
        </a>
      ) : null}
    </div>
  );
}
