import type { ApiDecimal } from '../api';
import { languageToLocale, type Language } from '../i18n';

export function formatMoney(
  value: ApiDecimal | null | undefined,
  language: Language = getRuntimeLanguage(),
): string {
  const amount = Number(value ?? 0);

  if (!Number.isFinite(amount)) {
    return '0.00';
  }

  return amount.toLocaleString(languageToLocale(language), {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatDate(
  value: string | null | undefined,
  language: Language = getRuntimeLanguage(),
): string {
  if (!value) {
    return language === 'ru' ? 'Не задано' : 'Not set';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString(languageToLocale(language));
}

export function toDateTimeInput(value: string | null | undefined): string {
  if (!value) {
    return '';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }

  const timezoneOffsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - timezoneOffsetMs).toISOString().slice(0, 16);
}

export function fromDateTimeInput(value: string): string | null {
  if (!value) {
    return null;
  }

  return new Date(value).toISOString();
}

export function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function compactText(value: string | null | undefined, fallback = 'Not provided'): string {
  return value && value.trim().length > 0 ? value : fallback;
}

function getRuntimeLanguage(): Language {
  return document.documentElement.lang === 'en' ? 'en' : 'ru';
}
