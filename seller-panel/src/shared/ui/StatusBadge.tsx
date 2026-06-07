import type { OrderStatus, ProductStatus, ReviewStatus } from '../api';
import { labelForEnum, useI18n } from '../i18n';

type StatusValue = ProductStatus | OrderStatus | ReviewStatus | 'ACTIVE' | 'INACTIVE';

const toneByStatus: Record<string, string> = {
  ACTIVE: 'success',
  APPROVED: 'success',
  DELIVERED: 'success',
  PROCESSING: 'info',
  SHIPPED: 'info',
  DRAFT: 'neutral',
  NEW: 'warning',
  PENDING: 'warning',
  OUT_OF_STOCK: 'warning',
  ARCHIVED: 'danger',
  CANCELLED: 'danger',
  REJECTED: 'danger',
  INACTIVE: 'neutral',
};

export function StatusBadge({ status, label }: { status: StatusValue; label?: string }) {
  const { t } = useI18n();
  const tone = toneByStatus[status] ?? 'neutral';

  return <span className={`status-badge status-${tone}`}>{label ?? labelForEnum(status, t)}</span>;
}
