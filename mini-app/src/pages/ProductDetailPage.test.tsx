import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProductDetailPage } from './ProductDetailPage';
import type { Product } from '../shared/api';
import { readFileSync } from 'node:fs';

const apiMocks = vi.hoisted(() => ({
  addCartItem: vi.fn(),
  addFavorite: vi.fn(),
  createProductReview: vi.fn(),
  getCart: vi.fn(),
  getFavorites: vi.fn(),
  getProduct: vi.fn(),
  getProductReviews: vi.fn(),
  removeFavorite: vi.fn(),
  resolveProduct: vi.fn(),
}));

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  goBack: vi.fn(),
  route: {
    currentPath: '/product/10',
    pathname: '/product/10',
  },
}));

vi.mock('../shared/api', () => ({
  addCartItem: apiMocks.addCartItem,
  addFavorite: apiMocks.addFavorite,
  createProductReview: apiMocks.createProductReview,
  getCart: apiMocks.getCart,
  getFavorites: apiMocks.getFavorites,
  getProduct: apiMocks.getProduct,
  getProductReviews: apiMocks.getProductReviews,
  removeFavorite: apiMocks.removeFavorite,
  resolveProduct: apiMocks.resolveProduct,
  toApiErrorMessage: (error: unknown) => error instanceof Error ? error.message : String(error),
}));

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('../shared/router/RouterProvider', () => ({
  getAuthPath: (path: string) => `/auth?returnTo=${encodeURIComponent(path)}`,
  getNumericRouteParam: (pathname: string, prefix: string) => Number(pathname.slice(prefix.length)),
  getCategoryProductRouteParams: (pathname: string) => {
    const match = pathname.match(/^\/category\/([^/]+)\/product\/([^/]+)$/);
    return match ? { categorySlug: match[1], productSlug: match[2] } : null;
  },
  isFirstLevelRoutePath: (path: string) => {
    const url = new URL(path, window.location.origin);
    return ['/', '/main', '/categories', '/search', '/cart', '/profile'].includes(url.pathname);
  },
  Link: ({ children, to, ...props }: React.PropsWithChildren<{ to: string }>) => (
    <a href={to} {...props}>{children}</a>
  ),
  useRouter: () => ({
    currentPath: routerMocks.route.currentPath,
    pathname: routerMocks.route.pathname,
    navigate: routerMocks.navigate,
    goBack: routerMocks.goBack,
  }),
  withReturnTo: (path: string) => path,
}));

function mockProductDetail(product = productFixture(), cart = cartFixture()) {
  apiMocks.getProduct.mockResolvedValue(product);
  apiMocks.getProductReviews.mockResolvedValue({ items: [] });
  apiMocks.getFavorites.mockResolvedValue({ items: [] });
  apiMocks.getCart.mockResolvedValue(cart);
}

describe('ProductDetailPage sticky actions', () => {
  afterEach(() => {
    cleanup();
    routerMocks.route.currentPath = '/product/10';
    routerMocks.route.pathname = '/product/10';
    vi.clearAllMocks();
  });

  it('renders bottom-attached action buttons without duplicating the price', async () => {
    mockProductDetail();

    const { container } = render(<ProductDetailPage />);

    const buyButton = await screen.findByRole('button', { name: 'Купить сейчас' });
    const cartButton = screen.getByRole('button', { name: 'В корзину' });
    const cta = buyButton.closest('.detail-cta');
    const productInfoPrice = container.querySelector('.price-block strong')?.textContent;

    expect(cta).not.toBeNull();
    expect(cta?.classList.contains('detail-cta--bottom-attached')).toBe(true);
    expect(cartButton.closest('.detail-cta')).toBe(cta);
    expect(cta?.querySelector('.detail-cta__price')).toBeNull();
    expect(productInfoPrice).toBeTruthy();
    expect(cta?.textContent ?? '').not.toContain(productInfoPrice!);
  });

  it('keeps the buy-now button wired to checkout', async () => {
    mockProductDetail();
    apiMocks.addCartItem.mockResolvedValue(cartFixture());

    render(<ProductDetailPage />);

    fireEvent.click(await screen.findByRole('button', { name: 'Купить сейчас' }));

    await waitFor(() => expect(apiMocks.addCartItem).toHaveBeenCalledWith(10, 100, 1));
    await waitFor(() => expect(routerMocks.navigate).toHaveBeenCalledWith('/checkout'));
  });

  it('keeps the add-to-cart button wired to cart insertion', async () => {
    mockProductDetail();
    apiMocks.addCartItem.mockResolvedValue(cartFixture());

    render(<ProductDetailPage />);

    fireEvent.click(await screen.findByRole('button', { name: 'В корзину' }));

    await waitFor(() => expect(apiMocks.addCartItem).toHaveBeenCalledWith(10, 100, 1));
    expect(routerMocks.navigate).not.toHaveBeenCalled();
  });

  it('preserves disabled action buttons for unavailable variants', async () => {
    mockProductDetail(productFixture({
      variants: [{
        ...productFixture().variants[0],
        available_quantity: 0,
      }],
    }));

    render(<ProductDetailPage />);

    const buyButton = await screen.findByRole('button', { name: 'Купить сейчас' });
    const cartButton = screen.getByRole('button', { name: 'В корзину' });

    expect((buyButton as HTMLButtonElement).disabled).toBe(true);
    expect((cartButton as HTMLButtonElement).disabled).toBe(true);
  });

  it('preserves loading state inside the bottom-attached action bar', async () => {
    let resolveCart: ((cart: ReturnType<typeof cartFixture>) => void) | undefined;
    mockProductDetail();
    apiMocks.addCartItem.mockReturnValue(new Promise((resolve) => {
      resolveCart = resolve;
    }));

    render(<ProductDetailPage />);

    fireEvent.click(await screen.findByRole('button', { name: 'В корзину' }));

    const loadingButton = await screen.findByRole('button', { name: 'Добавляем...' });
    expect((loadingButton as HTMLButtonElement).disabled).toBe(true);
    expect(loadingButton.closest('.detail-cta')?.classList.contains('detail-cta--bottom-attached')).toBe(true);

    resolveCart?.(cartFixture());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Перейти в корзину' })).toBeTruthy());
  });
});

describe('ProductDetailPage description', () => {
  afterEach(() => {
    cleanup();
    routerMocks.route.currentPath = '/product/10';
    routerMocks.route.pathname = '/product/10';
    vi.clearAllMocks();
  });

  it('renders the size fit hint between product info and variants', async () => {
    apiMocks.getProduct.mockResolvedValue(productFixture());
    apiMocks.getProductReviews.mockResolvedValue({ items: [] });
    apiMocks.getFavorites.mockResolvedValue({ items: [] });
    apiMocks.getCart.mockResolvedValue(cartFixture());

    const { container } = render(<ProductDetailPage />);

    const hint = await screen.findByText('Мы подбираем размер по росту и весу.');
    const productInfoCard = container.querySelector('.product-gallery + .detail-card');
    const variantCard = container.querySelector('.variant-selector-card');

    expect(hint.closest('.product-fit-hint')).not.toBeNull();
    expect(productInfoCard).not.toBeNull();
    expect(variantCard).not.toBeNull();
    expect(productInfoCard!.compareDocumentPosition(hint) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(hint.compareDocumentPosition(variantCard!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('renders product brand above the product title when brand exists', async () => {
    apiMocks.getProduct.mockResolvedValue(productFixture());
    apiMocks.getProductReviews.mockResolvedValue({ items: [] });
    apiMocks.getFavorites.mockResolvedValue({ items: [] });
    apiMocks.getCart.mockResolvedValue(cartFixture());

    const { container } = render(<ProductDetailPage />);

    const title = await screen.findByRole('heading', { level: 1, name: 'Line Break Hoodie' });
    const brand = container.querySelector('.product-detail-brand');
    const styles = readFileSync('src/styles.css', 'utf-8');

    expect(brand).not.toBeNull();
    expect(brand?.textContent).toBe('ICON STORE');
    expect(brand?.classList.contains('product-detail-title')).toBe(true);
    expect(title.classList.contains('product-detail-title')).toBe(true);
    expect(brand!.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(styles).toMatch(/\.product-detail-title\s*{[^}]*font-size:\s*22px/s);
    expect(styles).toMatch(/\.product-detail-title\s*{[^}]*font-weight:\s*900/s);
  });

  it('does not render an empty product brand row', async () => {
    apiMocks.getProduct.mockResolvedValue(productFixture({ brand: '   ' }));
    apiMocks.getProductReviews.mockResolvedValue({ items: [] });
    apiMocks.getFavorites.mockResolvedValue({ items: [] });
    apiMocks.getCart.mockResolvedValue(cartFixture());

    const { container } = render(<ProductDetailPage />);

    expect(await screen.findByRole('heading', { level: 1, name: 'Line Break Hoodie' })).toBeTruthy();
    expect(container.querySelector('.product-detail-brand')).toBeNull();
  });

  it('does not duplicate the brand when the product title already starts with it', async () => {
    apiMocks.getProduct.mockResolvedValue(productFixture({ name: 'ICON STORE Line Break Hoodie' }));
    apiMocks.getProductReviews.mockResolvedValue({ items: [] });
    apiMocks.getFavorites.mockResolvedValue({ items: [] });
    apiMocks.getCart.mockResolvedValue(cartFixture());

    const { container } = render(<ProductDetailPage />);

    expect(await screen.findByRole('heading', { level: 1, name: 'ICON STORE Line Break Hoodie' })).toBeTruthy();
    expect(container.querySelector('.product-detail-brand')).toBeNull();
  });

  it('preserves newline text rendering in collapsed and expanded states', async () => {
    const styles = readFileSync('src/styles.css', 'utf-8');
    const description = [
      'MONCLER',
      'Комплект футболка-штаны',
      'Сезон: весна/лето',
      'Размеры: М L XL XXL 3XL',
      'Размер подберем по росту и весу',
    ].join('\n');
    apiMocks.getProduct.mockResolvedValue(productFixture({ description }));
    apiMocks.getProductReviews.mockResolvedValue({ items: [] });
    apiMocks.getFavorites.mockResolvedValue({ items: [] });
    apiMocks.getCart.mockResolvedValue(cartFixture());

    const { container } = render(<ProductDetailPage />);

    expect(await screen.findByText('MONCLER', { exact: false })).toBeTruthy();
    const copy = container.querySelector<HTMLParagraphElement>('.description-card__copy');
    expect(copy).not.toBeNull();
    expect(copy?.textContent).toBe(description);
    expect(copy?.classList.contains('is-collapsed')).toBe(true);
    expect(styles).toMatch(/\.description-card__copy\s*{[^}]*white-space:\s*pre-line/s);

    const toggle = container.querySelector<HTMLButtonElement>('.description-card__toggle');
    expect(toggle).not.toBeNull();
    fireEvent.click(toggle!);

    await waitFor(() => expect(copy?.classList.contains('is-collapsed')).toBe(false));
    expect(copy?.textContent).toBe(description);
  });
});

describe('ProductDetailPage resolver preselection', () => {
  afterEach(() => {
    cleanup();
    routerMocks.route.currentPath = '/product/10';
    routerMocks.route.pathname = '/product/10';
    vi.clearAllMocks();
  });

  it('opens category product links through resolver and preselects the SKU variant', async () => {
    routerMocks.route.currentPath = '/category/futbolki/product/line-break-hoodie?sku=00002';
    routerMocks.route.pathname = '/category/futbolki/product/line-break-hoodie';
    apiMocks.resolveProduct.mockResolvedValue({
      product: productFixture({
        variants: [
          { ...productFixture().variants[0], id: 100, color: 'White', size: 'M', sku: '00001' },
          { ...productFixture().variants[0], id: 101, color: 'Black', size: 'L', sku: '00002' },
        ],
      }),
      route_context: {
        category: { id: 1, slug: 'futbolki', name: 'Футболки' },
        product_slug: 'line-break-hoodie',
        requested_sku: '00002',
        selected_variant_id: 101,
        selected_variant_sku: '00002',
        variant_status: 'selected',
      },
    });
    apiMocks.getProductReviews.mockResolvedValue({ items: [] });
    apiMocks.getFavorites.mockResolvedValue({ items: [] });
    apiMocks.getCart.mockResolvedValue(cartFixture());

    const { container } = render(<ProductDetailPage />);

    await waitFor(() => expect(apiMocks.resolveProduct).toHaveBeenCalledWith({
      category_slug: 'futbolki',
      product_slug: 'line-break-hoodie',
      sku: '00002',
    }));
    expect(apiMocks.getProduct).not.toHaveBeenCalled();
    expect(container.querySelector('.color-button.is-selected')?.textContent).toContain('Black');
    expect(container.querySelector('.variant-button.is-selected')?.textContent).toContain('L');
  });

  it('falls back to the default available variant when resolver SKU is invalid', async () => {
    routerMocks.route.currentPath = '/category/futbolki/product/line-break-hoodie?sku=bad';
    routerMocks.route.pathname = '/category/futbolki/product/line-break-hoodie';
    apiMocks.resolveProduct.mockResolvedValue({
      product: productFixture({
        variants: [
          { ...productFixture().variants[0], id: 100, color: 'White', size: 'M', sku: '00001' },
          { ...productFixture().variants[0], id: 101, color: 'Black', size: 'L', sku: '00002' },
        ],
      }),
      route_context: {
        category: { id: 1, slug: 'futbolki', name: 'Футболки' },
        product_slug: 'line-break-hoodie',
        requested_sku: 'bad',
        selected_variant_id: null,
        selected_variant_sku: null,
        variant_status: 'sku_not_found',
      },
    });
    apiMocks.getProductReviews.mockResolvedValue({ items: [] });
    apiMocks.getFavorites.mockResolvedValue({ items: [] });
    apiMocks.getCart.mockResolvedValue(cartFixture());

    const { container } = render(<ProductDetailPage />);

    await waitFor(() => expect(apiMocks.resolveProduct).toHaveBeenCalled());
    expect(container.querySelector('.color-button.is-selected')?.textContent).toContain('White');
    expect(container.querySelector('.variant-button.is-selected')?.textContent).toContain('M');
  });

  it('keeps an out-of-stock resolver-selected variant highlighted with disabled purchase actions', async () => {
    routerMocks.route.currentPath = '/category/futbolki/product/line-break-hoodie?sku=00002';
    routerMocks.route.pathname = '/category/futbolki/product/line-break-hoodie';
    apiMocks.resolveProduct.mockResolvedValue({
      product: productFixture({
        is_available: true,
        variants: [
          { ...productFixture().variants[0], id: 100, color: 'White', size: 'M', sku: '00001' },
          {
            ...productFixture().variants[0],
            id: 101,
            color: 'Black',
            size: 'L',
            sku: '00002',
            available_quantity: 0,
          },
        ],
      }),
      route_context: {
        category: { id: 1, slug: 'futbolki', name: 'Футболки' },
        product_slug: 'line-break-hoodie',
        requested_sku: '00002',
        selected_variant_id: 101,
        selected_variant_sku: '00002',
        variant_status: 'out_of_stock',
      },
    });
    apiMocks.getProductReviews.mockResolvedValue({ items: [] });
    apiMocks.getFavorites.mockResolvedValue({ items: [] });
    apiMocks.getCart.mockResolvedValue(cartFixture());

    const { container } = render(<ProductDetailPage />);

    const buyButton = await screen.findByRole('button', { name: 'Купить сейчас' });
    expect(container.querySelector('.color-button.is-selected')?.textContent).toContain('Black');
    expect(container.querySelector('.variant-button.is-selected')?.textContent).toContain('L');
    expect((buyButton as HTMLButtonElement).disabled).toBe(true);
  });
});

function productFixture(overrides: Partial<Product> = {}): Product {
  return {
    id: 10,
    name: 'Line Break Hoodie',
    slug: 'line-break-hoodie',
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
    images: [],
    variants: [{
      id: 100,
      product_id: 10,
      size: 'M',
      color: null,
      sku: 'SKU-M',
      available_quantity: 3,
      is_active: true,
    }],
    is_available: true,
    created_at: '2026-06-27T00:00:00Z',
    ...overrides,
  };
}

function cartFixture() {
  return {
    id: 1,
    user_id: 1,
    items: [],
    total: '0.00',
    quantity_total: 0,
    distinct_item_count: 0,
    selected_total: '0.00',
    selected_quantity_total: 0,
    selected_distinct_item_count: 0,
    created_at: '2026-06-27T00:00:00Z',
    updated_at: '2026-06-27T00:00:00Z',
  };
}
