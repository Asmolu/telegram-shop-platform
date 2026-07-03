import { formatPrice } from '../utils/format';
import { normalizeAssetUrl } from '../utils/images';

export function LookSourceHeader({
  imageUrl,
  subtotal,
  title,
}: {
  imageUrl?: string | null;
  subtotal?: string | number | null;
  title: string;
}) {
  const normalizedImageUrl = normalizeAssetUrl(imageUrl);

  return (
    <div className="look-source-header">
      <span className="look-source-header__image">
        {normalizedImageUrl ? (
          <img src={normalizedImageUrl} alt="" width={48} height={48} loading="lazy" decoding="async" />
        ) : (
          <span>{title.slice(0, 1).toUpperCase()}</span>
        )}
      </span>
      <div>
        <strong>Куплено из образа: {title}</strong>
        {subtotal !== undefined && subtotal !== null ? (
          <small>{formatPrice(subtotal)}</small>
        ) : null}
      </div>
    </div>
  );
}
