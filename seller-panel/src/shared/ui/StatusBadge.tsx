import type {
  ManualPaymentStatus,
  OrderStatus,
  ProductStatus,
  ReturnRequestStatus,
  ReviewStatus,
} from '../api';
import { labelForEnum, useI18n } from '../i18n';

type StatusValue =
  | ProductStatus
  | OrderStatus
  | ReviewStatus
  | ReturnRequestStatus
  | ManualPaymentStatus
  | 'ACTIVE'
  | 'INACTIVE';

const toneByStatus: Record<string, string> = {
  ACTIVE: 'success',
  APPROVED: 'success',
  COMPLETED: 'success',
  DELIVERED: 'success',
  PROCESSING: 'info',
  SHIPPED: 'info',
  DRAFT: 'neutral',
  NEW: 'warning',
  PENDING: 'warning',
  SUBMITTED: 'warning',
  OUT_OF_STOCK: 'warning',
  ARCHIVED: 'danger',
  CANCELLED: 'danger',
  REJECTED: 'danger',
  EXPIRED: 'danger',
  INACTIVE: 'neutral',
};

export function StatusBadge({ status, label }: { status: StatusValue; label?: string }) {
  const { t } = useI18n();
  const tone = toneByStatus[status] ?? 'neutral';

  return <span className={`status-badge status-${tone}`}>{label ?? labelForEnum(status, t)}</span>;
}
