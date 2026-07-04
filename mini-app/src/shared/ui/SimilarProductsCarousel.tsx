import React from 'react';
import type { Product } from '../api';
import { ProductCard } from './ProductCard';

type SimilarProductsCarouselProps = {
  products: Product[];
  loading?: boolean;
  onAddToCart?: (product: Product) => void | Promise<void>;
};

export function SimilarProductsCarousel({
  products,
  loading = false,
  onAddToCart,
}: SimilarProductsCarouselProps) {
  if (!loading && products.length === 0) {
    return null;
  }

  return (
    <section
      className="detail-card similar-products-section"
      aria-busy={loading ? 'true' : undefined}
    >
      <h2>Похожие товары</h2>
      <div className="similar-products-carousel" data-swipe-back-ignore>
        {loading
          ? [0, 1, 2].map((index) => <SimilarProductSkeleton key={index} />)
          : products.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                onAddToCart={onAddToCart}
              />
            ))}
      </div>
    </section>
  );
}

function SimilarProductSkeleton() {
  return (
    <div className="product-card product-card--skeleton similar-products-skeleton">
      <div className="skeleton skeleton-image" />
      <div className="skeleton skeleton-line skeleton-line--wide" />
      <div className="skeleton skeleton-line" />
      <div className="skeleton skeleton-button" />
    </div>
  );
}
