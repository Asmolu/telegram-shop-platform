import React from 'react';
import { useRouter } from '../shared/router/RouterProvider';
import { TopBar } from '../shared/ui';
import { getTelegramBotUrl } from '../shared/telegram/webApp';

const faqItems = [
  ['Как оформить заказ?', 'Добавьте товары в корзину, выберите размер, заполните контакты и нажмите «Оформить заказ».'],
  ['Как применить промокод?', 'Введите промокод в корзине или на странице оформления. Итог пересчитается автоматически.'],
  ['Как узнать статус заказа?', 'Откройте «Покупки» и вкладку «Заказы». Статус обновляется продавцом.'],
  ['Как подобрать размер?', 'На странице товара доступны размеры и остатки. Рост и вес можно оставить в комментарии к заказу.'],
  ['Как связаться с продавцом?', 'Используйте кнопку Telegram ниже или раздел поддержки в профиле.'],
  ['Как оставить отзыв?', 'Откройте товар после покупки, поставьте оценку и отправьте отзыв. Он появится после модерации.'],
];

export function FaqPage() {
  const { navigate } = useRouter();
  const [openIndex, setOpenIndex] = React.useState(0);
  const botUrl = getTelegramBotUrl();

  return (
    <div className="page">
      <TopBar title="FAQ" onBack={() => navigate('/main')} />
      <div className="accordion-list">
        {faqItems.map(([question, answer], index) => (
          <section className="accordion-item" key={question}>
            <button type="button" onClick={() => setOpenIndex(openIndex === index ? -1 : index)}>
              <span>{question}</span>
              <strong>{openIndex === index ? '−' : '+'}</strong>
            </button>
            {openIndex === index ? <p>{answer}</p> : null}
          </section>
        ))}
      </div>
      {botUrl ? (
        <a className="primary-button full-width" href={botUrl}>
          Связаться с продавцом
        </a>
      ) : null}
    </div>
  );
}
