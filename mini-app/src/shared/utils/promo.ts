import { ApiClientError, toApiErrorMessage } from '../api';

export function normalizePromoCode(value: string) {
  return value.trim().toUpperCase();
}

export function getPromoErrorMessage(error: unknown) {
  if (error instanceof ApiClientError) {
    const detail = error.details && typeof error.details === 'object' && 'detail' in error.details
      ? (error.details as { detail?: unknown }).detail
      : null;
    const source = `${typeof detail === 'string' ? detail : error.message}`.toLowerCase();

    if (error.status === 404 || source.includes('not found')) {
      return 'Промокод не найден.';
    }

    if (source.includes('inactive')) {
      return 'Промокод сейчас неактивен.';
    }

    if (source.includes('expired')) {
      return 'Срок действия промокода истек.';
    }

    if (source.includes('not active yet')) {
      return 'Промокод пока не действует.';
    }

    if (source.includes('per-user')) {
      return 'Вы уже использовали этот промокод.';
    }

    if (source.includes('usage limit')) {
      return 'Лимит промокода уже исчерпан.';
    }
  }

  return toApiErrorMessage(error);
}
