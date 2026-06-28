const priceFormatter = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
});

function normalizePrice(value: string | number | null | undefined) {
  const amount = Number(value ?? 0);
  return Number.isFinite(amount) ? amount : 0;
}

export function formatPrice(value: string | number | null | undefined) {
  return priceFormatter.format(normalizePrice(value));
}

export function formatCompactPrice(value: string | number | null | undefined) {
  return priceFormatter
    .formatToParts(normalizePrice(value))
    .map((part) => (part.type === 'group' ? '\u202f' : part.value))
    .join('');
}

export function getDisplayOldPrice(price: string | number | null | undefined, oldPrice?: string | number | null, compareAtPrice?: string | number | null) {
  const current = Number(price ?? 0);
  const candidate = Number(oldPrice ?? compareAtPrice ?? 0);

  if (!Number.isFinite(current) || !Number.isFinite(candidate) || candidate <= current) {
    return null;
  }

  return candidate;
}

export type DiscountBadgeTier = 1 | 2 | 3 | 4 | 5;

export function getDiscountPercent(price: string | number | null | undefined, oldPrice?: string | number | null) {
  const current = Number(price ?? 0);
  const previous = Number(oldPrice ?? 0);

  if (!Number.isFinite(current) || !Number.isFinite(previous) || previous <= current) {
    return null;
  }

  const percent = Math.round(((previous - current) / previous) * 100);
  return percent > 0 ? percent : null;
}

export function formatDiscountPercent(price: string | number | null | undefined, oldPrice?: string | number | null) {
  const percent = getDiscountPercent(price, oldPrice);

  if (!percent) {
    return null;
  }

  return `-${percent}%`;
}

export function getDiscountBadgeTier(percent: number | null | undefined): DiscountBadgeTier | null {
  const normalized = Number(percent);

  if (!Number.isFinite(normalized) || normalized <= 0) {
    return null;
  }

  if (normalized <= 20) return 1;
  if (normalized <= 40) return 2;
  if (normalized <= 60) return 3;
  if (normalized <= 80) return 4;
  return 5;
}

export function formatDate(value: string | null | undefined) {
  if (!value) {
    return '';
  }

  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(new Date(value));
}

export function pluralizeProducts(count: number) {
  const mod10 = count % 10;
  const mod100 = count % 100;

  if (mod10 === 1 && mod100 !== 11) {
    return `${count} товар`;
  }

  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${count} товара`;
  }

  return `${count} товаров`;
}

export function formatOrderStatus(status: string) {
  const labels: Record<string, string> = {
    NEW: 'Новый',
    PROCESSING: 'В обработке',
    SHIPPED: 'Отправлен',
    DELIVERED: 'Доставлен',
    CANCELLED: 'Отменён',
  };

  return labels[status] ?? status;
}

export function getUserDisplayName(user?: { first_name?: string | null; last_name?: string | null; username?: string | null } | null) {
  if (!user) {
    return 'Гость';
  }

  const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ').trim();
  return fullName || (user.username ? `@${user.username}` : 'Покупатель');
}
