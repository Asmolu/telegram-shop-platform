import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useQuickCartPicker } from './useQuickCartPicker';
import type { Product, ProductVariant } from '../../shared/api';

const apiMocks = vi.hoisted(() => ({
  addCartItem: vi.fn(),
}));

vi.mock('../../shared/api', () => ({
  addCartItem: apiMocks.addCartItem,
  toApiErrorMessage: (error: unknown) => error instanceof Error ? error.message : String(error),
}));

describe('useQuickCartPicker', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it('adds a one-variant product immediately and emits cart-updated after success', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    apiMocks.addCartItem.mockResolvedValue(cartFixture());

    render(<QuickCartHarness product={productFixture({ variants: [variantFixture({ id: 101 })] })} />);
    fireEvent.click(screen.getByRole('button', { name: 'quick add' }));

    await waitFor(() => expect(apiMocks.addCartItem).toHaveBeenCalledWith(10, 101, 1));
    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'miniapp:cart-updated' }));
    expect(screen.getByTestId('notice').textContent).not.toBe('');
  });

  it('opens a picker when multiple variants are available', async () => {
    render(
      <QuickCartHarness
        product={productFixture({
          variants: [
            variantFixture({ id: 101, size: 'M' }),
            variantFixture({ id: 102, size: 'L' }),
          ],
        })}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'quick add' }));

    expect(apiMocks.addCartItem).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'M' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'L' })).toBeTruthy();
  });

  it('adds the selected variant once when the size button is clicked twice quickly', async () => {
    let resolveAdd: (value: unknown) => void = () => undefined;
    apiMocks.addCartItem.mockImplementation(() => new Promise((resolve) => {
      resolveAdd = resolve;
    }));
    render(
      <QuickCartHarness
        product={productFixture({
          variants: [
            variantFixture({ id: 101, size: 'M' }),
            variantFixture({ id: 102, size: 'L' }),
          ],
        })}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'quick add' }));
    const sizeButton = screen.getByRole('button', { name: 'M' });
    fireEvent.click(sizeButton);
    fireEvent.click(sizeButton);

    expect(apiMocks.addCartItem).toHaveBeenCalledTimes(1);
    expect(apiMocks.addCartItem).toHaveBeenCalledWith(10, 101, 1);
    resolveAdd(cartFixture());

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});

function QuickCartHarness({ product }: { product: Product }) {
  const [notice, setNotice] = React.useState('');
  const quickCart = useQuickCartPicker({
    requireAuth: () => true,
    onNotice: setNotice,
  });

  return (
    <>
      <button type="button" onClick={() => void quickCart.addToCart(product)}>
        quick add
      </button>
      <span data-testid="notice">{notice}</span>
      {quickCart.picker}
    </>
  );
}

function productFixture(overrides: Partial<Product> = {}): Product {
  return {
    id: 10,
    name: 'Quick Cart Hoodie',
    slug: 'quick-cart-hoodie',
    brand: 'ICON STORE',
    description: null,
    base_price: '1000.00',
    old_price: null,
    compare_at_price: null,
    size_grid: 'clothing_alpha',
    image_badge_type: 'none',
    image_badge_text: null,
    image_badge_color: null,
    image_badge_position: null,
    variants: [],
    is_available: true,
    created_at: '2026-06-27T00:00:00Z',
    ...overrides,
  };
}

function variantFixture(overrides: Partial<ProductVariant> = {}): ProductVariant {
  return {
    id: 101,
    product_id: 10,
    size: 'M',
    color: null,
    sku: 'SKU-M',
    available_quantity: 3,
    is_active: true,
    ...overrides,
  };
}

function cartFixture() {
  return {
    id: 1,
    user_id: 1,
    items: [],
    total: '0.00',
    quantity_total: 1,
    distinct_item_count: 1,
    selected_total: '1000.00',
    selected_quantity_total: 1,
    selected_distinct_item_count: 1,
    created_at: '2026-06-27T00:00:00Z',
    updated_at: '2026-06-27T00:00:00Z',
  };
}
