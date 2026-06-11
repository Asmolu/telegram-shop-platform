import type { Banner } from '../api';

export type BannerAction =
  | { kind: 'copy'; value: string }
  | { kind: 'internal'; value: string }
  | { kind: 'external'; value: string };

export function getBannerAction(banner: Banner): BannerAction | null {
  if (banner.target_type === 'promo' && banner.promo_code) {
    return { kind: 'copy', value: banner.promo_code };
  }

  if (banner.target_type === 'product' && banner.target_id) {
    return { kind: 'internal', value: `/product/${banner.target_id}` };
  }

  if (banner.target_type === 'category' && banner.target_id) {
    return { kind: 'internal', value: `/category/${banner.target_id}` };
  }

  if (banner.target_type === 'external_url' && banner.external_url) {
    return { kind: 'external', value: banner.external_url };
  }

  return null;
}

export function getBannerCtaLabel(action: BannerAction | null) {
  return action?.kind === 'copy' ? 'Скопировать' : action ? 'Смотреть' : null;
}

export async function copyTextToClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand('copy');
  textarea.remove();
  if (!copied) {
    throw new Error('Clipboard copy failed');
  }
}
