import React from 'react';
import type { Product } from '../api';
import { getProductImageItems } from '../utils/images';

type ProductImageCarouselVariant = 'card' | 'detail';

export function ProductImageCarousel({
  product,
  variant = 'detail',
}: {
  product: Product;
  variant?: ProductImageCarouselVariant;
}) {
  const trackRef = React.useRef<HTMLDivElement | null>(null);
  const [activeIndex, setActiveIndex] = React.useState(0);
  const images = getProductImageItems(product);
  const slides = images.length > 0 ? images : [{ id: 'fallback', url: null, alt: product.name }];
  const fallbackLetter = product.name.slice(0, 1).toUpperCase();
  const hasMultipleImages = slides.length > 1;

  React.useEffect(() => {
    setActiveIndex(0);
    trackRef.current?.scrollTo({ left: 0 });
  }, [product.id]);

  const handleScroll = React.useCallback(() => {
    const track = trackRef.current;

    if (!track) {
      return;
    }

    const nextIndex = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
    setActiveIndex(Math.min(Math.max(nextIndex, 0), slides.length - 1));
  }, [slides.length]);

  function scrollToSlide(index: number) {
    const track = trackRef.current;

    if (!track) {
      return;
    }

    track.scrollTo({
      left: track.clientWidth * index,
      behavior: 'smooth',
    });
  }

  return (
    <div className={`product-image-carousel product-image-carousel--${variant}`}>
      <div className="product-image-carousel__track" ref={trackRef} onScroll={handleScroll}>
        {slides.map((slide, index) => (
          <div className="product-image-carousel__slide" key={slide.id}>
            {slide.url ? (
              <img
                src={slide.url}
                alt={slide.alt}
                draggable={false}
                loading={variant === 'detail' && index === 0 ? 'eager' : 'lazy'}
              />
            ) : (
              <div className="image-fallback">
                <span>{fallbackLetter}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {hasMultipleImages ? (
        <>
          <div className="product-image-carousel__dots" aria-hidden={variant === 'card' ? 'true' : undefined}>
            {slides.map((slide, index) => (
              variant === 'detail' ? (
                <button
                  className={activeIndex === index ? 'is-active' : ''}
                  key={slide.id}
                  type="button"
                  aria-label={`Image ${index + 1}`}
                  onClick={() => scrollToSlide(index)}
                />
              ) : (
                <span className={activeIndex === index ? 'is-active' : ''} key={slide.id} />
              )
            ))}
          </div>
          {variant === 'detail' ? (
            <span className="product-image-carousel__counter">
              {activeIndex + 1} / {slides.length}
            </span>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
