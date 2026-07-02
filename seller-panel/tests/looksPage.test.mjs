import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/shared/api/client.ts', import.meta.url), 'utf8');
const typesSource = readFileSync(new URL('../src/shared/api/types.ts', import.meta.url), 'utf8');
const i18nSource = readFileSync(new URL('../src/shared/i18n/index.tsx', import.meta.url), 'utf8');
const pageSource = readFileSync(
  new URL('../src/pages/Looks/LooksPage.tsx', import.meta.url),
  'utf8',
);

test('looks navigation and routes are wired', () => {
  assert.match(appSource, /\/looks/);
  assert.match(appSource, /nav\.looks/);
  assert.match(appSource, /\/looks\/new/);
  assert.match(appSource, /lookEditMatch/);
  assert.match(appSource, /LooksPage/);
  assert.match(appSource, /LookEditorPage/);
  assert.match(i18nSource, /'nav\.looks': 'Образы'/);
});

test('seller API exposes looks admin methods and types', () => {
  assert.match(apiSource, /looks: \{/);
  assert.match(apiSource, /\/looks\/admin/);
  assert.match(apiSource, /\/looks\/admin\/\$\{lookId\}/);
  assert.match(apiSource, /\/looks\/admin\/\$\{lookId\}\/images/);
  assert.match(apiSource, /deleteImage/);
  assert.match(typesSource, /export type LookStatus/);
  assert.match(typesSource, /export interface Look/);
  assert.match(typesSource, /export interface LookCreatePayload/);
  assert.match(typesSource, /export interface LookUpdatePayload/);
});

test('looks list renders filters badges price and archive action', () => {
  assert.match(pageSource, /api\.looks\.listAdmin/);
  assert.match(pageSource, /api\.products\.listAdmin/);
  assert.match(pageSource, /statusFilter/);
  assert.match(pageSource, /looks\.hiddenBadge/);
  assert.match(pageSource, /calculateLookDefaultPrice/);
  assert.match(pageSource, /api\.looks\.archive/);
  assert.match(i18nSource, /looks\.status\.DRAFT/);
  assert.match(i18nSource, /looks\.status\.ACTIVE/);
  assert.match(i18nSource, /looks\.status\.ARCHIVED/);
});

test('look editor has required fields defaults and validation', () => {
  assert.match(pageSource, /status: 'DRAFT'/);
  assert.match(pageSource, /isListed: true/);
  assert.match(pageSource, /looks\.title/);
  assert.match(pageSource, /looks\.slug/);
  assert.match(pageSource, /looks\.isListed/);
  assert.match(pageSource, /looks\.searchPriority/);
  assert.match(pageSource, /slugPattern/);
  assert.match(pageSource, /activeNeedsProduct/);
  assert.match(pageSource, /activeNeedsDefault/);
  assert.match(pageSource, /activeNeedsActiveProducts/);
  assert.match(pageSource, /quantityInvalid/);
  assert.match(pageSource, /formatRequestError/);
});

test('look editor supports product components and hidden product badges', () => {
  assert.match(pageSource, /api\.products\.listAdmin/);
  assert.match(pageSource, /addProductToLook/);
  assert.match(pageSource, /duplicateProduct/);
  assert.match(pageSource, /isDefaultSelected/);
  assert.match(pageSource, /hasMultipleActiveColors/);
  assert.match(pageSource, /looks\.multiColorWarning/);
  assert.match(pageSource, /!product\.is_listed/);
  assert.match(pageSource, /moveItem/);
  assert.match(pageSource, /removeItem/);
});

test('look image section handles unsaved saved upload and delete states', () => {
  assert.match(pageSource, /looks\.saveBeforeImages/);
  assert.match(pageSource, /api\.looks\.uploadImage/);
  assert.match(pageSource, /api\.looks\.deleteImage/);
  assert.match(pageSource, /accept="image\/jpeg,image\/png,image\/webp"/);
  assert.match(pageSource, /looks\.primaryImage/);
  assert.match(pageSource, /looks\.imageUploaded/);
  assert.match(pageSource, /looks\.imageDeleted/);
});
