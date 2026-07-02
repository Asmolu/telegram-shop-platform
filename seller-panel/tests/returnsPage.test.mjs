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
  assert.match(typesSource, /export interface ReturnRequest/);
  assert.match(typesSource, /export type ReturnRequestStatus/);
});

test('returns page renders list detail attachments and decision actions', () => {
  assert.match(pageSource, /api\.returns\.list/);
  assert.match(pageSource, /api\.returns\.get/);
  assert.match(pageSource, /api\.returns\.approve/);
  assert.match(pageSource, /api\.returns\.reject/);
  assert.match(pageSource, /returns\.attachments/);
  assert.match(pageSource, /returns\.approve/);
  assert.match(pageSource, /returns\.reject/);
  assert.match(pageSource, /StatusBadge status=\{returnRequest\.status\}/);
});
