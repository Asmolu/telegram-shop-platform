import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const pageSource = readFileSync(
  new URL('../src/pages/Settings/SettingsPage.tsx', import.meta.url),
  'utf8',
);
const clientSource = readFileSync(new URL('../src/shared/api/client.ts', import.meta.url), 'utf8');
const typesSource = readFileSync(new URL('../src/shared/api/types.ts', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

test('settings page exposes paid confirmation banner controls', () => {
  assert.match(pageSource, /Баннер после подтверждения оплаты/);
  assert.match(pageSource, /api\.paymentSuccessBanner\.get/);
  assert.match(pageSource, /api\.paymentSuccessBanner\.update/);
  assert.match(pageSource, /api\.paymentSuccessBanner\.delete/);
  assert.match(pageSource, /api\.banners\.uploadImage\(file, undefined, 'vertical_banner'\)/);
  assert.match(pageSource, /accept="image\/\*"/);
  assert.match(pageSource, /paid-banner-preview__media/);
  assert.match(pageSource, /Загрузите изображение перед включением баннера/);
});

test('seller api client has paid confirmation banner endpoints and payload types', () => {
  assert.match(clientSource, /paymentSuccessBanner/);
  assert.match(clientSource, /\/settings\/admin\/payment-success-banner/);
  assert.match(typesSource, /interface PaymentSuccessBannerSettings/);
  assert.match(typesSource, /interface PaymentSuccessBannerSettingsPayload/);
});

test('settings page exposes seller contact URL controls', () => {
  assert.match(pageSource, /Контакты продавца/);
  assert.match(pageSource, /Telegram URL/);
  assert.match(pageSource, /WhatsApp URL/);
  assert.match(pageSource, /Instagram URL/);
  assert.match(pageSource, /api\.sellerContacts\.get/);
  assert.match(pageSource, /api\.sellerContacts\.update/);
  assert.match(clientSource, /\/settings\/admin\/seller-contacts/);
  assert.match(typesSource, /interface SellerContactSettings/);
  assert.match(typesSource, /interface SellerContactSettingsPayload/);
});

test('paid confirmation banner preview keeps vertical mobile aspect', () => {
  assert.match(stylesSource, /paid-banner-settings-grid/);
  assert.match(stylesSource, /aspect-ratio: 9 \/ 16/);
});
