import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { RouterProvider } from '../router/RouterProvider';
import { ProductCard } from '../ui/ProductCard';
import { ProductImageCarousel } from '../ui/ProductImageCarousel';
import type { Product } from '../api';
import { getProductImageItems, getProductImageUrl } from './images';

describe('product image variants', () => {
  afterEach(() => {
    cleanup();
  });

  it('selects card derivatives and builds a derivative-only srcset', () => {
    const product = productFixture();

    const item = getProductImageItems(product, 'card')[0];

    expect(getProductImageUrl(product, 'card')).toBe('http://localhost:8000/uploads/products/card.webp');
    expect(item.srcSet).toContain('/uploads/products/thumb.webp 240w');
    expect(item.srcSet).toContain('/uploads/products/card.webp 480w');
    expect(item.srcSet).not.toContain('original.jpg');
    expect(item.sizes).toBe('(max-width: 480px) 50vw, 240px');
  });

  it('falls back to the legacy image url when variants are missing', () => {
    const product = productFixture({
      images: [{
        ...productFixture().images![0],
        thumbnail_url: null,
        card_url: null,
        detail_url: null,
        thumbnail_path: null,
        card_path: null,
        detail_path: null,
        image_variants: null,
      }],
    });

    expect(getProductImageUrl(product, 'card')).toBe(
      'http://localhost:8000/uploads/products/original.jpg',
    );
  });

  it('selects compact card DTO image fields without a gallery payload', () => {
    const product = productFixture({
      images: undefined,
      image_url: '/uploads/products/card.webp',
      thumbnail_image_url: '/uploads/products/thumb.webp',
    });

    const item = getProductImageItems(product, 'card')[0];

    expect(item.url).toBe('http://localhost:8000/uploads/products/card.webp');
    expect(item.srcSet).toContain('/uploads/products/thumb.webp 240w');
    expect(item.srcSet).toContain('/uploads/products/card.webp 480w');
    expect(getProductImageUrl(product, 'thumbnail')).toBe(
      'http://localhost:8000/uploads/products/thumb.webp',
    );
  });

  it('renders detail derivatives with dimensions and lazy slide loading', () => {
    render(<ProductImageCarousel product={productFixture()} variant="detail" />);

    const image = screen.getByAltText('Hoodie');
    expect(image.getAttribute('src')).toBe('http://localhost:8000/uploads/products/detail.webp');
    expect(image.getAttribute('width')).toBe('1200');
    expect(image.getAttribute('height')).toBe('1500');
    expect(image.getAttribute('loading')).toBe('eager');
    expect(image.getAttribute('decoding')).toBe('async');
  });

  it('shows a fallback after a broken image', () => {
    render(<ProductImageCarousel product={productFixture()} variant="card" />);

    fireEvent.error(screen.getByAltText('Hoodie'));

    expect(screen.getByText('H')).toBeTruthy();
  });

  it('allows only the explicitly critical card image to use high priority', () => {
    render(
      <RouterProvider>
        <ProductCard
          product={productFixture({ id: 1 })}
          imageLoading="eager"
          imageFetchPriority="high"
        />
        <ProductCard product={productFixture({ id: 2 })} />
      </RouterProvider>,
    );

    const highPriorityImages = screen
      .getAllByAltText('Hoodie')
      .filter((image) => image.getAttribute('fetchpriority') === 'high');

    expect(highPriorityImages).toHaveLength(1);
    expect(screen.getAllByAltText('Hoodie')[0].getAttribute('src')).toBe(
      'http://localhost:8000/uploads/products/card.webp',
    );
    expect(screen.getAllByAltText('Hoodie')[1].getAttribute('loading')).toBe('lazy');
  });

  it('applies the expected discount tier class on product cards', () => {
    render(
      <RouterProvider>
        <ProductCard product={productFixture({ base_price: '62.00', old_price: '100.00' })} />
      </RouterProvider>,
    );

    const badge = screen.getByText('-38%');

    expect(badge.classList.contains('product-discount-badge')).toBe(true);
    expect(badge.classList.contains('discount-badge--tier-2')).toBe(true);
  });

  it('does not render a discount badge without an effective discount', () => {
    const { container } = render(
      <RouterProvider>
        <ProductCard product={productFixture({ base_price: '100.00', old_price: null })} />
      </RouterProvider>,
    );

    expect(container.querySelector('.product-discount-badge')).toBeNull();
  });
});

function productFixture(overrides: Partial<Product> = {}): Product {
  const product: Product = {
    id: 1,
    name: 'Hoodie',
    slug: 'hoodie',
    brand: 'ICON STORE',
    description: 'Warm',
    base_price: '100.00',
    old_price: null,
    size_grid: 'clothing_alpha',
    image_badge_type: 'none',
    image_badge_text: null,
    image_badge_color: null,
    image_badge_position: null,
    status: 'ACTIVE',
    category_id: null,
    category: null,
    categories: [],
    tags: [],
    images: [
      {
        id: 1,
        product_id: 1,
        file_path: 'products/original.jpg',
        url: '/uploads/products/original.jpg',
        image_url: '/uploads/products/original.jpg',
        thumbnail_path: 'products/thumb.webp',
        card_path: 'products/card.webp',
        detail_path: 'products/detail.webp',
        thumbnail_url: '/uploads/products/thumb.webp',
        card_url: '/uploads/products/card.webp',
        detail_url: '/uploads/products/detail.webp',
        image_variants: {
          thumbnail: '/uploads/products/thumb.webp',
          card: '/uploads/products/card.webp',
          detail: '/uploads/products/detail.webp',
        },
        alt_text: null,
        position: 0,
        is_primary: true,
        original_filename: 'original.jpg',
        mime_type: 'image/jpeg',
        size_bytes: 123,
        created_at: '2026-06-24T00:00:00Z',
      },
    ],
    variants: [],
    related_products: [],
    is_available: true,
    created_at: '2026-06-24T00:00:00Z',
    updated_at: '2026-06-24T00:00:00Z',
  };
  return { ...product, ...overrides };
}
