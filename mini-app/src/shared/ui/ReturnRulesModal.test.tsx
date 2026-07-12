import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReturnRulesModal } from './ReturnRulesModal';

describe('ReturnRulesModal', () => {
  afterEach(() => cleanup());

  it('shows every rule, excludes navigation copy, and gates Continue with consent', () => {
    render(<ReturnRulesModal onCancel={vi.fn()} onContinue={vi.fn()} returnFocusTo={null} />);

    expect(screen.getByRole('dialog', { name: 'Правила возврата' })).toBeTruthy();
    expect(screen.getByText(/в течение 24 часов/)).toBeTruthy();
    expect(screen.getByText(/только для товаров, разрешённых к возврату/)).toBeTruthy();
    expect(screen.getByText(/Товар не должен быть в употреблении/)).toBeTruthy();
    expect(screen.getByText(/хотя бы одно фото или видео/)).toBeTruthy();
    expect(screen.getByText('Стоимость доставки не возвращается.')).toBeTruthy();
    expect(screen.getByText('Продавец вправе отказать в возврате без объяснения причин.')).toBeTruthy();
    expect(screen.queryByText(/Покупки.*Заказы/)).toBeNull();

    const checkbox = screen.getByRole('checkbox') as HTMLInputElement;
    const continueButton = screen.getByRole('button', { name: 'Продолжить оформление' }) as HTMLButtonElement;
    expect(checkbox.checked).toBe(false);
    expect(continueButton.disabled).toBe(true);
    fireEvent.click(checkbox);
    expect(continueButton.disabled).toBe(false);
    fireEvent.click(checkbox);
    expect(continueButton.disabled).toBe(true);
  });

  it('supports Cancel, Escape, backdrop close, and focus restoration', () => {
    const origin = document.createElement('button');
    document.body.append(origin);
    const onCancel = vi.fn();
    const { unmount } = render(
      <ReturnRulesModal onCancel={onCancel} onContinue={vi.fn()} returnFocusTo={origin} />,
    );

    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Отмена' }));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
    fireEvent.mouseDown(document.querySelector('.return-rules-overlay') as HTMLElement);
    expect(onCancel).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(onCancel).toHaveBeenCalledTimes(3);
    unmount();
    expect(document.activeElement).toBe(origin);
    origin.remove();
  });

  it('starts unchecked each time it is mounted', () => {
    const props = { onCancel: vi.fn(), onContinue: vi.fn(), returnFocusTo: null };
    const { unmount } = render(<ReturnRulesModal {...props} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
    unmount();

    render(<ReturnRulesModal {...props} />);
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
  });
});
