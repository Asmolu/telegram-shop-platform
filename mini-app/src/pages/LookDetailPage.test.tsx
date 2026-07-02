import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  addLookToCart,
  getLook,
  type Cart,
  type LookDetail,
} from '../shared/api';
import { LookDetailPage } from './LookDetailPage';

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  route: {
    currentPath: '/looks/summer-look',
    pathname: '/looks/summer-look',
    searchParams: new URLSearchParams(),
  },
}));

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('../shared/router/RouterProvider', () => ({
  getAuthPath: (path: string) => `/auth?returnTo=${encodeURIComponent(path)}`,
  isFirstLevelRoutePath: () => false,
  Link: ({ children, to, ...props }: React.PropsWithChildren<{ to: string }>) => (
    <a href={to} {...props}>{children}</a>
  ),
  useRouter: () => ({
    currentPath: routerMocks.route.currentPath,
    pathname: routerMocks.route.pathname,
    navigate: routerMocks.navigate,
    searchParams: routerMocks.route.searchParams,
    goBack: vi.fn(),
  }),
  withReturnTo: (path: string, returnTo?: string | null) => (
    returnTo ? `${path}?returnTo=${encodeURIComponent(returnTo)}` : path
  ),
}));

vi.mock('../shared/api', () => ({
  addLookToCart: vi.fn().mockResolvedValue({ message: 'Образ добавлен в корзину.', cart: cartFixture() }),
  getApiBaseUrl: vi.fn(() => ''),
  getLook: vi.fn().mockResolvedValue(lookFixture()),
  toApiErrorMessage: (error: unknown) => error instanceof Error ? error.message : String(error),
}));

describe('LookDetailPage', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    routerMocks.route.currentPath = '/looks/summer-look';
    routerMocks.route.pathname = '/looks/summer-look';
    vi.mocked(getLook).mockResolvedValue(lookFixture());
    vi.mocked(addLookToCart).mockResolvedValue({ message: 'Образ добавлен в корзину.', cart: cartFixture() });
  });

  it('renders image, title, description, selected components and size chips', async () => {
    render(<LookDetailPage />);

    expect(await screen.findByRole('heading', { level: 1, name: 'Summer Look' })).toBeTruthy();
    await waitFor(() => expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false));
    expect(screen.getByText('Light city outfit')).toBeTruthy();
    expect(screen.getByText(/1\s*500/)).toBeTruthy();
    expect(screen.getByRole('button', { name: /Hoodie/ }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: /Cap/ }).getAttribute('aria-pressed')).toBe('true');
    expect(within(screen.getByLabelText('Доступные размеры')).getByRole('button', { name: /M/ })).toBeTruthy();
  });

  it('updates dynamic price when a component is unselected', async () => {
    const { container } = render(<LookDetailPage />);

    const capButton = await screen.findByRole('button', { name: /Cap/ });
    fireEvent.click(capButton);

    expect(capButton.getAttribute('aria-pressed')).toBe('false');
    expect(container.querySelector('.price-stack strong')?.textContent).toMatch(/1\s*000/);
  });

  it('blocks unselecting the last selected component', async () => {
    render(<LookDetailPage />);

    fireEvent.click(await screen.findByRole('button', { name: /Cap/ }));
    const hoodieButton = screen.getByRole('button', { name: /Hoodie/ });
    fireEvent.click(hoodieButton);

    expect(await screen.findByText('В образе должен остаться хотя бы один товар.')).toBeTruthy();
    expect(hoodieButton.getAttribute('aria-pressed')).toBe('true');
  });

  it('adds selected items to cart through the atomic Look endpoint', async () => {
    render(<LookDetailPage />);

    await waitFor(() => expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'В корзину' }));

    await waitFor(() => expect(addLookToCart).toHaveBeenCalledWith('summer-look', {
      selected_item_ids: [1, 2],
      size: 'M',
    }));
    expect(await screen.findByText('Образ добавлен в корзину.')).toBeTruthy();
  });

  it('uses the Look cart endpoint for buy-now and navigates to checkout', async () => {
    render(<LookDetailPage />);

    await waitFor(() => expect((screen.getByRole('button', { name: 'Купить сейчас' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'Купить сейчас' }));

    await waitFor(() => expect(addLookToCart).toHaveBeenCalled());
    await waitFor(() => expect(routerMocks.navigate).toHaveBeenCalledWith('/checkout?returnTo=%2Flooks%2Fsummer-look'));
  });

  it('handles ONE_SIZE-only Looks automatically', async () => {
    vi.mocked(getLook).mockResolvedValueOnce(lookFixture({
      items: [oneSizeItem()],
      default_selected_item_ids: [2],
      available_sizes: ['ONE_SIZE'],
      default_price: '500.00',
    }));

    render(<LookDetailPage />);

    expect((await screen.findAllByText('Единый размер')).length).toBeGreaterThan(0);
    await waitFor(() => expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'В корзину' }));

    await waitFor(() => expect(addLookToCart).toHaveBeenCalledWith('summer-look', {
      selected_item_ids: [2],
      size: 'ONE_SIZE',
    }));
  });

  it('disables checkout when selected products have no common size', async () => {
    vi.mocked(getLook).mockResolvedValueOnce(lookFixture({
      items: [
        {
          ...lookFixture().items[0],
          available_sizes: ['M'],
        },
        {
          ...lookFixture().items[0],
          look_item_id: 3,
          product_id: 12,
          product_slug: 'pants',
          product_name: 'Pants',
          product: {
            product_id: 12,
            product_slug: 'pants',
            name: 'Pants',
            brand: 'ICON',
            image_url: '/uploads/products/pants.webp',
            price: '1200.00',
            old_price: null,
          },
          available_sizes: ['L'],
          price: '1200.00',
        },
      ],
      default_selected_item_ids: [1, 3],
      available_sizes: [],
    }));

    render(<LookDetailPage />);

    expect((await screen.findAllByText('Нет общего доступного размера для выбранных товаров.')).length).toBeGreaterThan(0);
    expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows backend add-to-cart errors cleanly', async () => {
    vi.mocked(addLookToCart).mockRejectedValueOnce(new Error('Недостаточно товара'));

    render(<LookDetailPage />);

    await waitFor(() => expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'В корзину' }));

    expect(await screen.findByText('Недостаточно товара')).toBeTruthy();
  });

  it('links included products back to product detail with returnTo', async () => {
    render(<LookDetailPage />);

    await screen.findAllByText('Hoodie');
    const productLink = screen.getAllByText('Hoodie')
      .map((element) => element.closest('a'))
      .find((link): link is HTMLAnchorElement => link !== null);

    expect(productLink).not.toBeNull();
    expect(productLink?.getAttribute('href')).toBe('/product/10?returnTo=%2Flooks%2Fsummer-look');
  });
});

function lookFixture(overrides: Partial<LookDetail> = {}): LookDetail {
  return {
    id: 5,
    slug: 'summer-look',
    title: 'Summer Look',
    description: 'Light city outfit',
    images: [{
      id: 1,
      look_id: 5,
      file_path: 'looks/summer.webp',
      url: '/uploads/looks/summer.webp',
      image_url: '/uploads/looks/summer.webp',
      original_filename: 'summer.webp',
      mime_type: 'image/webp',
      size_bytes: 1000,
      alt_text: 'Summer Look',
      position: 0,
      is_primary: true,
      created_at: '2026-07-01T00:00:00Z',
    }],
    items: [sizedItem(), oneSizeItem()],
    default_selected_item_ids: [1, 2],
    default_price: '1500.00',
    old_price: null,
    available_sizes: ['M', 'L'],
    is_available: true,
    ...overrides,
  };
}

function sizedItem() {
  return {
    look_item_id: 1,
    product: {
      product_id: 10,
      product_slug: 'hoodie',
      name: 'Hoodie',
      brand: 'ICON',
      image_url: '/uploads/products/hoodie.webp',
      price: '1000.00',
      old_price: null,
    },
    product_id: 10,
    product_slug: 'hoodie',
    product_name: 'Hoodie',
    brand: 'ICON',
    primary_image_url: '/uploads/products/hoodie.webp',
    price: '1000.00',
    old_price: null,
    quantity: 1,
    is_default_selected: true,
    available_sizes: ['M', 'L'],
    one_size: false,
    is_available: true,
  };
}

function oneSizeItem() {
  return {
    look_item_id: 2,
    product: {
      product_id: 11,
      product_slug: 'cap',
      name: 'Cap',
      brand: 'ICON',
      image_url: '/uploads/products/cap.webp',
      price: '500.00',
      old_price: null,
    },
    product_id: 11,
    product_slug: 'cap',
    product_name: 'Cap',
    brand: 'ICON',
    primary_image_url: '/uploads/products/cap.webp',
    price: '500.00',
    old_price: null,
    quantity: 1,
    is_default_selected: true,
    available_sizes: ['ONE_SIZE'],
    one_size: true,
    is_available: true,
  };
}

function cartFixture(): Cart {
  return {
    id: 1,
    user_id: 1,
    items: [],
    total: '1500.00',
    quantity_total: 2,
    distinct_item_count: 2,
    selected_total: '1500.00',
    selected_quantity_total: 2,
    selected_distinct_item_count: 2,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
  };
}
