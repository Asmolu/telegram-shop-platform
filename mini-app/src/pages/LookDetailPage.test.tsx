import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  addLookToCart,
  getLook,
  getLookSimilarProducts,
  type Cart,
  type LookDetail,
  type Product,
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
    <a
      href={to}
      onClick={(event) => {
        event.preventDefault();
        routerMocks.navigate(to);
      }}
      {...props}
    >
      {children}
    </a>
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
  getLookSimilarProducts: vi.fn().mockResolvedValue({
    items: [],
    meta: { limit: 12, offset: 0, total: 0 },
  }),
  toApiErrorMessage: (error: unknown) => error instanceof Error ? error.message : String(error),
}));

beforeEach(() => {
  vi.mocked(getLookSimilarProducts).mockResolvedValue({
    items: [],
    meta: { limit: 12, offset: 0, total: 0 },
  });
});

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
    expect(screen.getByText('Light city outfit')).toBeTruthy();
    expect(screen.getByText(/1\s*500/)).toBeTruthy();
    expect(screen.getByRole('button', { name: /Hoodie/ }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: /Cap/ }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('heading', { level: 2, name: 'Размер одежды' })).toBeTruthy();
    expect(within(screen.getByLabelText('Доступные размеры одежды')).getByRole('button', { name: /M/ })).toBeTruthy();
    await waitFor(() => expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false));
  });

  it('fetches and renders similar products below included Look products', async () => {
    vi.mocked(getLookSimilarProducts).mockResolvedValueOnce({
      items: [
        productFixture({ id: 22, name: 'Similar Tee', slug: 'similar-tee' }),
        productFixture({ id: 10, name: 'Included Duplicate', slug: 'included-duplicate' }),
      ],
      meta: { limit: 12, offset: 0, total: 2 },
    });

    render(<LookDetailPage />);

    await waitFor(() => expect(getLookSimilarProducts).toHaveBeenCalledWith(
      'summer-look',
      12,
      { networkImpact: 'local' },
    ));
    const heading = await screen.findByRole('heading', { level: 2, name: 'Похожие товары' });
    const includedSection = screen.getByRole('heading', { level: 2, name: 'Товары в образе' });
    expect(includedSection.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText('Similar Tee')).toBeTruthy();
    expect(screen.queryByText('Included Duplicate')).toBeNull();
  });

  it('hides similar products when the Look endpoint returns empty', async () => {
    render(<LookDetailPage />);

    await waitFor(() => expect(getLookSimilarProducts).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.queryByRole('heading', { level: 2, name: 'Похожие товары' })).toBeNull();
    });
  });

  it('continues to render Look detail if similar products fail', async () => {
    vi.mocked(getLookSimilarProducts).mockRejectedValueOnce(new Error('network failed'));

    render(<LookDetailPage />);

    expect(await screen.findByRole('heading', { level: 1, name: 'Summer Look' })).toBeTruthy();
    await waitFor(() => expect(getLookSimilarProducts).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.queryByRole('heading', { level: 2, name: 'Похожие товары' })).toBeNull();
    });
  });

  it('preserves returnTo when opening a similar product from a Look', async () => {
    vi.mocked(getLookSimilarProducts).mockResolvedValueOnce({
      items: [productFixture({ id: 22, name: 'Similar Tee', slug: 'similar-tee' })],
      meta: { limit: 12, offset: 0, total: 1 },
    });

    render(<LookDetailPage />);

    const similarProductLink = (await screen.findByText('Similar Tee')).closest('a');
    expect(similarProductLink).not.toBeNull();
    expect(similarProductLink?.getAttribute('href')).toBe('/product/22?returnTo=%2Flooks%2Fsummer-look');
    fireEvent.click(similarProductLink!);

    expect(routerMocks.navigate).toHaveBeenCalledWith('/product/22?returnTo=%2Flooks%2Fsummer-look');
  });

  it('opens an old Look slug and replaces the route with the canonical slug', async () => {
    routerMocks.route.currentPath = '/looks/old-look?returnTo=%2Fmain';
    routerMocks.route.pathname = '/looks/old-look';
    vi.mocked(getLook).mockResolvedValueOnce(lookFixture({ slug: 'current-look' }));

    render(<LookDetailPage />);

    await waitFor(() => expect(getLook).toHaveBeenCalledWith('old-look'));
    expect(routerMocks.navigate).toHaveBeenCalledWith(
      '/looks/current-look?returnTo=%2Fmain',
      { replace: true },
    );
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

    fireEvent.click(
      within(await screen.findByLabelText('Доступные размеры одежды')).getByRole('button', {
        name: /M/,
      }),
    );
    await waitFor(() => expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'В корзину' }));

    await waitFor(() => expect(addLookToCart).toHaveBeenCalledWith('summer-look', {
      selected_item_ids: [1, 2],
      clothing_size: 'M',
      footwear_size: null,
    }));
    expect(await screen.findByText('Образ добавлен в корзину.')).toBeTruthy();
  });

  it('uses the Look cart endpoint for buy-now and navigates to checkout', async () => {
    render(<LookDetailPage />);

    fireEvent.click(
      within(await screen.findByLabelText('Доступные размеры одежды')).getByRole('button', {
        name: /M/,
      }),
    );
    await waitFor(() => expect((screen.getByRole('button', { name: 'Купить сейчас' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'Купить сейчас' }));

    await waitFor(() => expect(addLookToCart).toHaveBeenCalled());
    await waitFor(() => expect(routerMocks.navigate).toHaveBeenCalledWith('/checkout?returnTo=%2Flooks%2Fsummer-look'));
  });

  it('shows footwear selector for footwear-only Looks', async () => {
    vi.mocked(getLook).mockResolvedValueOnce(lookFixture({
      items: [footwearItem()],
      default_selected_item_ids: [3],
      default_price: '2200.00',
      available_sizes: ['42', '43'],
      available_clothing_sizes: [],
      available_footwear_sizes: ['42', '43'],
      requires_clothing_size: false,
      requires_footwear_size: true,
    }));

    render(<LookDetailPage />);

    expect(await screen.findByRole('heading', { level: 2, name: 'Размер обуви' })).toBeTruthy();
    expect(screen.queryByRole('heading', { level: 2, name: 'Размер одежды' })).toBeNull();
    await waitFor(() => expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false));

    fireEvent.click(within(screen.getByLabelText('Доступные размеры обуви')).getByRole('button', { name: /42/ }));
    await waitFor(() => expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false));
  });

  it('shows clothing and footwear selectors for mixed Looks and sends both sizes', async () => {
    vi.mocked(getLook).mockResolvedValueOnce(lookFixture({
      items: [sizedItem(), footwearItem()],
      default_selected_item_ids: [1, 3],
      default_price: '3200.00',
      available_sizes: ['M', 'L'],
      available_clothing_sizes: ['M', 'L'],
      available_footwear_sizes: ['42', '43'],
      requires_clothing_size: true,
      requires_footwear_size: true,
    }));

    render(<LookDetailPage />);

    expect(await screen.findByRole('heading', { level: 2, name: 'Размер одежды' })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 2, name: 'Размер обуви' })).toBeTruthy();
    expect(screen.queryByText('Нет общего доступного размера для выбранных товаров.')).toBeNull();
    await waitFor(() => expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false));

    fireEvent.click(within(screen.getByLabelText('Доступные размеры одежды')).getByRole('button', { name: /M/ }));
    expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(within(screen.getByLabelText('Доступные размеры обуви')).getByRole('button', { name: /42/ }));
    await waitFor(() => expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false));

    fireEvent.click(screen.getByRole('button', { name: 'В корзину' }));

    await waitFor(() => expect(addLookToCart).toHaveBeenCalledWith('summer-look', {
      selected_item_ids: [1, 3],
      clothing_size: 'M',
      footwear_size: '42',
    }));
  });

  it('handles ONE_SIZE-only Looks automatically', async () => {
    vi.mocked(getLook).mockResolvedValueOnce(lookFixture({
      items: [oneSizeItem()],
      default_selected_item_ids: [2],
      available_sizes: ['ONE_SIZE'],
      available_clothing_sizes: [],
      available_footwear_sizes: [],
      requires_clothing_size: false,
      requires_footwear_size: false,
      default_price: '500.00',
    }));

    render(<LookDetailPage />);

    expect((await screen.findAllByText('Единый размер')).length).toBeGreaterThan(0);
    await waitFor(() => expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'В корзину' }));

    await waitFor(() => expect(addLookToCart).toHaveBeenCalledWith('summer-look', {
      selected_item_ids: [2],
      clothing_size: null,
      footwear_size: null,
    }));
  });

  it('disables checkout when selected clothing products have no available clothing size', async () => {
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
      available_clothing_sizes: [],
      available_footwear_sizes: [],
      requires_clothing_size: true,
      requires_footwear_size: false,
    }));

    render(<LookDetailPage />);

    expect((await screen.findAllByText('Нет доступного размера одежды для выбранных товаров.')).length).toBeGreaterThan(0);
    expect((screen.getByRole('button', { name: 'В корзину' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows backend add-to-cart errors cleanly', async () => {
    vi.mocked(addLookToCart).mockRejectedValueOnce(new Error('Недостаточно товара'));

    render(<LookDetailPage />);

    fireEvent.click(
      within(await screen.findByLabelText('Доступные размеры одежды')).getByRole('button', {
        name: /M/,
      }),
    );
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
    available_clothing_sizes: ['M', 'L'],
    available_footwear_sizes: [],
    requires_clothing_size: true,
    requires_footwear_size: false,
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
    size_group: 'CLOTHING' as const,
    available_sizes: ['M', 'L'],
    one_size: false,
    is_available: true,
  };
}

function footwearItem() {
  return {
    look_item_id: 3,
    product: {
      product_id: 12,
      product_slug: 'sneakers',
      name: 'Sneakers',
      brand: 'ICON',
      image_url: '/uploads/products/sneakers.webp',
      price: '2200.00',
      old_price: null,
    },
    product_id: 12,
    product_slug: 'sneakers',
    product_name: 'Sneakers',
    brand: 'ICON',
    primary_image_url: '/uploads/products/sneakers.webp',
    price: '2200.00',
    old_price: null,
    quantity: 1,
    is_default_selected: true,
    size_group: 'FOOTWEAR' as const,
    available_sizes: ['42', '43'],
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
    size_group: 'ONE_SIZE' as const,
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

function productFixture(overrides: Partial<Product> = {}): Product {
  return {
    id: 22,
    name: 'Similar Tee',
    slug: 'similar-tee',
    brand: 'ICON',
    description: null,
    base_price: '900.00',
    old_price: null,
    compare_at_price: null,
    size_grid: 'clothing_alpha',
    size_group: 'CLOTHING',
    image_badge_type: 'none',
    image_badge_text: null,
    image_badge_color: null,
    image_badge_position: null,
    images: [],
    variants: [{
      id: 220,
      product_id: 22,
      size: 'M',
      color: null,
      sku: 'SIM-M',
      available_quantity: 2,
      is_active: true,
    }],
    is_available: true,
    created_at: '2026-07-01T00:00:00Z',
    ...overrides,
  };
}
