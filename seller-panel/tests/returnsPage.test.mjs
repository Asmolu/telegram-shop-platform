import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/shared/api/client.ts', import.meta.url), 'utf8');
const typesSource = readFileSync(new URL('../src/shared/api/types.ts', import.meta.url), 'utf8');
const i18nSource = readFileSync(new URL('../src/shared/i18n/index.tsx', import.meta.url), 'utf8');
const pageSource = readFileSync(
  new URL('../src/pages/Returns/ReturnsPage.tsx', import.meta.url),
  'utf8',
);

test('/returns route and sidebar label are wired', () => {
  assert.match(appSource, /\/returns/);
  assert.match(appSource, /nav\.returns/);
  assert.match(appSource, /ReturnsPage/);
  assert.match(i18nSource, /'nav\.returns': 'Возвраты'/);
});

test('seller API exposes returns list detail and decisions', () => {
  assert.match(apiSource, /returns: \{/);
  assert.match(apiSource, /\/returns\/admin/);
  assert.match(apiSource, /\/returns\/admin\/\$\{returnRequestId\}\/approve/);
  assert.match(apiSource, /\/returns\/admin\/\$\{returnRequestId\}\/reject/);
  assert.match(apiSource, /\/returns\/admin\/\$\{returnRequestId\}\/complete/);
  assert.match(apiSource, /\/returns\/admin\/\$\{returnRequestId\}\/process/);
  assert.match(apiSource, /\/returns\/admin\/\$\{returnRequestId\}\/cancel/);
  assert.match(apiSource, /'COMPLETED'/);
  assert.match(apiSource, /'CANCELLED'/);
  assert.match(typesSource, /export interface ReturnRequest/);
  assert.match(typesSource, /export type ReturnRequestStatus/);
  assert.match(typesSource, /completed_at: string \| null/);
  assert.match(typesSource, /cancelled_at: string \| null/);
  assert.match(typesSource, /cancellation_comment: string \| null/);
  assert.match(typesSource, /export interface ReturnRefund/);
  assert.match(typesSource, /export interface ReturnProcessPayload/);
  assert.match(typesSource, /restocked_quantity: number/);
  assert.match(typesSource, /remaining_restockable_quantity: number/);
});

test('returns page renders list detail attachments and decision actions', () => {
  assert.match(pageSource, /api\.returns\.list/);
  assert.match(pageSource, /api\.returns\.get/);
  assert.match(pageSource, /api\.returns\.approve/);
  assert.match(pageSource, /api\.returns\.reject/);
  assert.match(pageSource, /api\.returns\.complete/);
  assert.match(pageSource, /api\.returns\.process/);
  assert.match(pageSource, /api\.returns\.cancel/);
  assert.match(pageSource, /returns\.attachments/);
  assert.match(pageSource, /returns\.approve/);
  assert.match(pageSource, /returns\.reject/);
  assert.match(pageSource, /returns\.complete/);
  assert.match(pageSource, /returns\.cancel/);
  assert.match(pageSource, /returnRequest\.status === 'APPROVED'/);
  assert.match(pageSource, /returnRequest\.status === 'PENDING'/);
  assert.match(pageSource, /completed_at/);
  assert.match(pageSource, /cancelled_at/);
  assert.match(pageSource, /status=\{returnRequest\.status\}/);
});

test('approved returns expose manual refund and restock processing controls', () => {
  assert.match(pageSource, /returns\.processing/);
  assert.match(pageSource, /returns\.refundAmount/);
  assert.match(pageSource, /returns\.refundMethod/);
  assert.match(pageSource, /returns\.refundComment/);
  assert.match(pageSource, /returns\.restockItem/);
  assert.match(pageSource, /returns\.restockQuantity/);
  assert.match(pageSource, /completeAfterProcessing/);
  assert.match(pageSource, /setRestockQuantities/);
  assert.match(pageSource, /type="checkbox"/);
  assert.match(pageSource, /type="number"/);
  assert.match(pageSource, /returnRequest\.status === 'APPROVED'/);
  assert.match(pageSource, /canProcess \?/);
});

test('return processing submission validates refund and restock limits', () => {
  assert.match(pageSource, /parseMoneyInput/);
  assert.match(pageSource, /refundAmountTooHigh/);
  assert.match(pageSource, /refundAmountNegative/);
  assert.match(pageSource, /restockQuantityTooHigh/);
  assert.match(pageSource, /restockQuantityNegative/);
  assert.match(pageSource, /restockNoVariant/);
  assert.match(pageSource, /itemRemainingRestockableQuantity/);
  assert.match(pageSource, /itemRestockedQuantity\(item\) \+ additionalQuantity/);
});

test('processed returns show refund and restock audit data', () => {
  assert.match(pageSource, /returnRequest\.refund/);
  assert.match(pageSource, /returns\.refundAudit/);
  assert.match(pageSource, /returns\.refundProcessedAt/);
  assert.match(pageSource, /returns\.refundProcessedBy/);
  assert.match(pageSource, /hasRestockAudit/);
  assert.match(pageSource, /returns\.restockAudit/);
});

test('items without variants cannot be restocked in the panel', () => {
  assert.match(pageSource, /!item\.product_variant_id/);
  assert.match(pageSource, /returns\.notRestockable/);
  assert.match(pageSource, /disabled=\{disabled \|\| actionBusy\}/);
});
