import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FaqPage } from './FaqPage';

const routerMocks = vi.hoisted(() => ({ topic: null as string | null }));

vi.mock('../shared/router/RouterProvider', () => ({
  useRouter: () => ({
    searchParams: new URLSearchParams(routerMocks.topic ? { topic: routerMocks.topic } : {}),
  }),
}));

vi.mock('../shared/ui', () => ({
  SellerContactCard: () => <div>Seller contacts</div>,
  TopBar: ({ title }: { title: string }) => <div>{title}</div>,
}));

describe('FaqPage return rules', () => {
  afterEach(() => {
    cleanup();
    routerMocks.topic = null;
  });

  it('places the return question immediately after the review question', () => {
    render(<FaqPage />);

    const questions = screen.getAllByRole('button').map((button) => button.textContent);
    const reviewIndex = questions.findIndex((text) => text?.includes('Как оставить отзыв?'));

    expect(questions[reviewIndex + 1]).toContain('Как совершить возврат товара?');
  });

  it('opens and closes the return answer while keeping one item open', () => {
    render(<FaqPage />);

    const returnButton = screen.getByRole('button', { name: /Как совершить возврат товара/ });
    fireEvent.click(returnButton);

    expect(screen.getByText(/Возврат можно оформить в течение 24 часов/)).toBeTruthy();
    expect(screen.queryByText(/Выберите товар, затем размер или цвет/)).toBeNull();

    fireEvent.click(returnButton);
    expect(screen.queryByText(/Возврат можно оформить в течение 24 часов/)).toBeNull();
  });

  it('opens topic=return directly and renders the required return rules', () => {
    routerMocks.topic = 'return';
    render(<FaqPage />);

    expect(screen.getByText(/Возврат можно оформить в течение 24 часов/)).toBeTruthy();
    expect(screen.getByText(/«Покупки» → вкладка «Заказы» → «Оформить возврат» под нужным заказом/)).toBeTruthy();
    expect(screen.queryByText(/«Подробнее».*⋮/)).toBeNull();
    expect(screen.getByText(/обязательно укажите причину и приложите хотя бы одно фото или видео/)).toBeTruthy();
    expect(screen.getByText(/Стоимость доставки не возвращается/)).toBeTruthy();
    expect(screen.getByText(/Продавец вправе отказать в возврате без объяснения причин/)).toBeTruthy();
  });
});
