import type {
  ProductImageBadgeColor,
  ProductImageBadgePosition,
  ProductImageBadgeType,
} from '../api';
import { useI18n } from '../i18n';

export interface ImageBadgeConfiguration {
  type: ProductImageBadgeType;
  text: string;
  color: ProductImageBadgeColor;
  position: ProductImageBadgePosition;
}

export const IMAGE_BADGE_TYPES: ProductImageBadgeType[] = [
  'none', 'new', 'sale', 'hit', 'exclusive', 'custom',
];

export const IMAGE_BADGE_COLORS: ProductImageBadgeColor[] = [
  'purple', 'pink', 'red', 'orange', 'blue', 'green', 'black', 'white',
];

export const IMAGE_BADGE_POSITIONS: ProductImageBadgePosition[] = [
  'top-left', 'top-right', 'bottom-left', 'bottom-right',
];

export function normalizeImageBadgeText(text: string): string {
  return text.trim();
}

export function isImageBadgeConfigurationValid(value: ImageBadgeConfiguration): boolean {
  return value.type !== 'custom' || normalizeImageBadgeText(value.text).length > 0;
}

export function getDefaultImageBadgeColor(type: ProductImageBadgeType): ProductImageBadgeColor {
  if (type === 'sale') return 'red';
  if (type === 'hit') return 'orange';
  return 'purple';
}

export function getDefaultImageBadgePosition(
  type: ProductImageBadgeType,
): ProductImageBadgePosition {
  return type === 'new' ? 'top-left' : 'bottom-left';
}

export function changeImageBadgeType(
  current: ImageBadgeConfiguration,
  type: ProductImageBadgeType,
): ImageBadgeConfiguration {
  const currentDefaultColor = getDefaultImageBadgeColor(current.type);
  const currentDefaultPosition = getDefaultImageBadgePosition(current.type);
  return {
    ...current,
    type,
    text: type === 'custom' ? current.text : '',
    color: current.color === currentDefaultColor ? getDefaultImageBadgeColor(type) : current.color,
    position: current.position === currentDefaultPosition
      ? getDefaultImageBadgePosition(type)
      : current.position,
  };
}

export function ImageBadgeConfigurator({
  value,
  onChange,
}: {
  value: ImageBadgeConfiguration;
  onChange: (value: ImageBadgeConfiguration) => void;
}) {
  const { t } = useI18n();
  const typeLabels: Record<ProductImageBadgeType, string> = {
    none: t('productEditor.badgeNone'),
    new: 'NEW',
    sale: t('productEditor.badgeSale'),
    hit: t('productEditor.badgeHit'),
    exclusive: t('productEditor.badgeExclusive'),
    custom: t('productEditor.badgeCustom'),
  };
  const colorLabels: Record<ProductImageBadgeColor, string> = {
    purple: t('productEditor.badgeColorPurple'), pink: t('productEditor.badgeColorPink'),
    red: t('productEditor.badgeColorRed'), orange: t('productEditor.badgeColorOrange'),
    blue: t('productEditor.badgeColorBlue'), green: t('productEditor.badgeColorGreen'),
    black: t('productEditor.badgeColorBlack'), white: t('productEditor.badgeColorWhite'),
  };
  const positionLabels: Record<ProductImageBadgePosition, string> = {
    'top-left': t('productEditor.badgePositionTopLeft'),
    'top-right': t('productEditor.badgePositionTopRight'),
    'bottom-left': t('productEditor.badgePositionBottomLeft'),
    'bottom-right': t('productEditor.badgePositionBottomRight'),
  };
  const previewText = value.type === 'custom'
    ? normalizeImageBadgeText(value.text) || typeLabels.custom
    : typeLabels[value.type];

  return (
    <div className="badge-editor" data-testid="shared-image-badge-configurator">
      <label className="field"><span>{t('productEditor.imageBadge')}</span>
        <select value={value.type} onChange={(event) => onChange(changeImageBadgeType(value, event.target.value as ProductImageBadgeType))}>
          {IMAGE_BADGE_TYPES.map((type) => <option key={type} value={type}>{typeLabels[type]}</option>)}
        </select>
      </label>
      {value.type === 'custom' ? <label className="field"><span>{t('productEditor.badgeText')}</span>
        <input maxLength={20} value={value.text} onChange={(event) => onChange({ ...value, text: event.target.value })} />
        <small className="field-hint">{value.text.length}/20</small>
      </label> : null}
      <label className="field"><span>{t('productEditor.badgeColor')}</span>
        <select value={value.color} onChange={(event) => onChange({ ...value, color: event.target.value as ProductImageBadgeColor })}>
          {IMAGE_BADGE_COLORS.map((color) => <option key={color} value={color}>{colorLabels[color]}</option>)}
        </select>
      </label>
      <label className="field"><span>{t('productEditor.badgePosition')}</span>
        <select value={value.position} onChange={(event) => onChange({ ...value, position: event.target.value as ProductImageBadgePosition })}>
          {IMAGE_BADGE_POSITIONS.map((position) => <option key={position} value={position}>{positionLabels[position]}</option>)}
        </select>
      </label>
      {value.type !== 'none' ? <div className="image-badge-preview-frame" aria-label={t('productEditor.badgePreview')}>
        <div className={`image-badge-preview image-badge-preview--color-${value.color} image-badge-preview--position-${value.position}`}>{previewText}</div>
      </div> : null}
    </div>
  );
}
