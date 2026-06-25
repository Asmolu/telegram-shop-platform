import React from 'react';
import type { Product } from '../api';
import {
  getProductBadgeColor,
  getProductBadgePosition,
  getProductImageBadge,
  getProductImageItems,
  type ProductImageItem,
} from '../utils/images';
import { getMotionAwareScrollBehavior } from '../utils/motion';
import { trackTelemetry } from '../telemetry';

type ProductImageCarouselVariant = 'card' | 'detail';
type CarouselSlide = Omit<ProductImageItem, 'url'> & { url: string | null };
let firstKeyImageReported = false;

export function ProductImageCarousel({
  product,
  variant = 'detail',
  loading,
  fetchPriority,
}: {
  product: Product;
  variant?: ProductImageCarouselVariant;
  loading?: 'eager' | 'lazy';
  fetchPriority?: 'high' | 'low' | 'auto';
}) {
  const trackRef = React.useRef<HTMLDivElement | null>(null);
  const scrollFrameRef = React.useRef(0);
  const [activeIndex, setActiveIndex] = React.useState(0);
  const [brokenImageIds, setBrokenImageIds] = React.useState<Set<string>>(new Set());
  const images = getProductImageItems(product, variant);
  const slides: CarouselSlide[] = images.length > 0
    ? images
    : [{
        id: 'fallback',
        url: null,
        alt: product.name,
        srcSet: undefined,
        sizes: undefined,
      }];
  const fallbackLetter = product.name.slice(0, 1).toUpperCase();
  const hasMultipleImages = slides.length > 1;
  const imageBadge = variant === 'detail' ? getProductImageBadge(product) : null;
  const imageBadgeColor = getProductBadgeColor(product);
  const imageBadgePosition = getProductBadgePosition(product);

  React.useEffect(() => {
    setActiveIndex(0);
    setBrokenImageIds(new Set());
    if (typeof trackRef.current?.scrollTo === 'function') {
      trackRef.current.scrollTo({ left: 0 });
    }
  }, [product.id]);

  React.useEffect(() => () => window.cancelAnimationFrame(scrollFrameRef.current), []);

  const updateActiveIndex = React.useCallback(() => {
    const track = trackRef.current;

    if (!track) {
      return;
    }

    const nextIndex = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
    setActiveIndex(Math.min(Math.max(nextIndex, 0), slides.length - 1));
  }, [slides.length]);

  const handleScroll = React.useCallback(() => {
    window.cancelAnimationFrame(scrollFrameRef.current);
    scrollFrameRef.current = window.requestAnimationFrame(updateActiveIndex);
  }, [updateActiveIndex]);

  function scrollToSlide(index: number) {
    const track = trackRef.current;

    if (!track) {
      return;
    }

    track.scrollTo({
      left: track.clientWidth * index,
      behavior: getMotionAwareScrollBehavior(),
    });
  }

  return (
    <div className={`product-image-carousel product-image-carousel--${variant}`}>
      <div className="product-image-carousel__track" ref={trackRef} onScroll={handleScroll}>
        {slides.map((slide, index) => (
          <div className="product-image-carousel__slide" key={slide.id}>
            {slide.url && !brokenImageIds.has(slide.id) && shouldLoadSlide(variant, activeIndex, index) ? (
              <img
                src={slide.url}
                srcSet={slide.srcSet}
                sizes={slide.sizes}
                alt={slide.alt}
                draggable={false}
                width={variant === 'detail' ? 1200 : 480}
                height={variant === 'detail' ? 1500 : 600}
                loading={loading ?? (variant === 'detail' && index === 0 ? 'eager' : 'lazy')}
                fetchPriority={index === 0 ? fetchPriority : undefined}
                decoding="async"
                onLoad={() => {
                  if (!firstKeyImageReported && index === 0) {
                    firstKeyImageReported = true;
                    trackTelemetry('first_key_image.loaded', {
                      route: window.location.pathname,
                      success: true,
                    });
                  }
                }}
                onError={() => {
                  setBrokenImageIds((current) => {
                    const next = new Set(current);
                    next.add(slide.id);
                    return next;
                  });
                }}
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
      {imageBadge ? (
        <span
          className={`product-image-badge product-image-badge--${product.image_badge_type} product-image-badge--color-${imageBadgeColor} product-image-badge--position-${imageBadgePosition}`}
        >
          {imageBadge}
        </span>
      ) : null}
    </div>
  );
}

function shouldLoadSlide(
  variant: ProductImageCarouselVariant,
  activeIndex: number,
  index: number,
) {
  if (variant === 'detail') {
    return index <= activeIndex + 1;
  }
  return index <= activeIndex + 1;
}
