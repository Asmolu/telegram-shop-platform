import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const pageSource = readFileSync(
  new URL('../src/pages/Orders/OrdersPage.tsx', import.meta.url),
  'utf8',
);
const typesSource = readFileSync(new URL('../src/shared/api/types.ts', import.meta.url), 'utf8');

test('seller order detail groups Look-sourced order items', () => {
  assert.match(pageSource, /isLookSourceOrderItem/);
  assert.match(pageSource, /order-look-group-row/);
  assert.match(pageSource, /Куплено из образа:/);
  assert.match(pageSource, /source_look_title/);
  assert.match(pageSource, /orderLookGroupSubtotal/);
});

test('seller order item type exposes nullable Look source metadata', () => {
  assert.match(typesSource, /source_type\?: ItemSourceType \| null/);
  assert.match(typesSource, /source_group_id\?: string \| null/);
  assert.match(typesSource, /source_look_id\?: number \| null/);
  assert.match(typesSource, /source_look_slug\?: string \| null/);
  assert.match(typesSource, /source_look_title\?: string \| null/);
  assert.match(typesSource, /source_look_image_url\?: string \| null/);
});
