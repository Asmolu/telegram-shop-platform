import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { applyGeneratedLookSlug } from '../src/pages/Looks/lookSlugAutofill.ts';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/shared/api/client.ts', import.meta.url), 'utf8');
const typesSource = readFileSync(new URL('../src/shared/api/types.ts', import.meta.url), 'utf8');
const i18nSource = readFileSync(new URL('../src/shared/i18n/index.tsx', import.meta.url), 'utf8');
const pageSource = readFileSync(
  new URL('../src/pages/Looks/LooksPage.tsx', import.meta.url),
  'utf8',
);
const productEditorSource = readFileSync(
  new URL('../src/pages/ProductEditor/ProductEditorPage.tsx', import.meta.url),
  'utf8',
);
const badgeConfiguratorSource = readFileSync(
  new URL('../src/shared/ui/ImageBadgeConfigurator.tsx', import.meta.url),
  'utf8',
);

test('Product and Look editors use the same image badge configurator contract', () => {
  assert.match(productEditorSource, /<ImageBadgeConfigurator/);
  assert.match(pageSource, /<ImageBadgeConfigurator/);
  assert.match(badgeConfiguratorSource, /'none', 'new', 'sale', 'hit', 'exclusive', 'custom'/);
  assert.match(badgeConfiguratorSource, /'purple', 'pink', 'red', 'orange', 'blue', 'green', 'black', 'white'/);
  assert.match(badgeConfiguratorSource, /'top-left', 'top-right', 'bottom-left', 'bottom-right'/);
  assert.match(badgeConfiguratorSource, /normalizeImageBadgeText/);
  assert.match(badgeConfiguratorSource, /isImageBadgeConfigurationValid/);
  assert.match(badgeConfiguratorSource, /text: type === 'custom' \? current\.text : ''/);
  assert.match(badgeConfiguratorSource, /image-badge-preview--color-\$\{value\.color\}/);
  assert.match(badgeConfiguratorSource, /image-badge-preview--position-\$\{value\.position\}/);
  assert.match(badgeConfiguratorSource, /productEditor\.badgeCustom/);
});

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
  assert.match(apiSource, /getNextSlugs/);
  assert.match(apiSource, /\/looks\/admin\/slugs\/next/);
  assert.match(apiSource, /\/looks\/admin\/\$\{lookId\}\/images/);
  assert.match(apiSource, /deleteImage/);
  assert.match(typesSource, /export type LookStatus/);
  assert.match(typesSource, /export interface Look/);
  assert.match(typesSource, /export interface LookSlugList/);
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

test('new look editor can apply a generated numeric look slug', () => {
  assert.equal(
    applyGeneratedLookSlug({
      mode: 'create',
      currentSlug: '',
      generatedSlug: '00017',
      wasManuallyEdited: false,
    }),
    '00017',
  );
});

test('look manual slug edits are not overwritten by async generation', () => {
  assert.equal(
    applyGeneratedLookSlug({
      mode: 'create',
      currentSlug: '',
      generatedSlug: '00018',
      wasManuallyEdited: true,
    }),
    '',
  );
  assert.equal(
    applyGeneratedLookSlug({
      mode: 'create',
      currentSlug: 'manual-look',
      generatedSlug: '00018',
      wasManuallyEdited: false,
    }),
    'manual-look',
  );
});

test('editing an existing look does not apply generated look slugs', () => {
  assert.equal(
    applyGeneratedLookSlug({
      mode: 'edit',
      currentSlug: 'existing-look',
      generatedSlug: '00019',
      wasManuallyEdited: false,
    }),
    'existing-look',
  );
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
  assert.match(pageSource, /formatLookRequestError/);
});

test('look editor requests and fills backend generated slugs only for new looks', () => {
  assert.match(pageSource, /api\.looks\.getNextSlugs\(1\)/);
  assert.match(pageSource, /if \(mode !== 'create'\)/);
  assert.match(pageSource, /slug: applyGeneratedLookSlug/);
  assert.match(pageSource, /manualSlugEditRef\.current = false/);
  assert.match(pageSource, /manualSlugEditRef\.current = true/);
  assert.match(pageSource, /setFormError\(t\('looks\.slugAutofillFailed'\)\)/);
  assert.match(i18nSource, /looks\.slugAutofillFailed/);
  assert.match(i18nSource, /Slug is generated automatically/);
  assert.match(pageSource, /slugAutofillRequestIdRef/);
});

test('look editor preserves loaded slugs and sends slug in create payloads', () => {
  assert.match(pageSource, /mode === 'edit' && lookId \? api\.looks\.getAdmin\(lookId\)/);
  assert.match(pageSource, /slug: loadedLook\.slug/);
  assert.match(pageSource, /loadNextLookSlug\(\)/);
  assert.match(pageSource, /slug: form\.slug\.trim\(\)/);
});

test('look editor disables saves and guards against double submit while saving', () => {
  assert.match(pageSource, /const savingRef = useRef\(false\)/);
  assert.match(pageSource, /if \(savingRef\.current\)/);
  assert.match(pageSource, /savingRef\.current = true/);
  assert.match(pageSource, /savingRef\.current = false/);
  assert.match(pageSource, /disabled=\{saving\}/);
  assert.match(pageSource, /type="submit"/);
});

test('look editor ignores stale save errors after a newer save request wins', () => {
  assert.match(pageSource, /const saveRequestIdRef = useRef\(0\)/);
  assert.match(pageSource, /saveRequestIdRef\.current = requestId/);
  assert.match(pageSource, /saveRequestIdRef\.current !== requestId/);
  assert.match(pageSource, /saveRequestIdRef\.current === requestId/);
  assert.match(pageSource, /setFormError\(null\)/);
});

test('look editor maps backend slug conflicts to a clear localized error', () => {
  assert.match(pageSource, /formatLookRequestError\(requestError, t\)/);
  assert.match(pageSource, /error\.status === 409/);
  assert.match(pageSource, /isSlugConflictMessage/);
  assert.match(pageSource, /looks\.slugTaken/);
  assert.match(i18nSource, /'looks\.slugTaken': 'Slug уже занят'/);
  assert.match(i18nSource, /'looks\.slugTaken': 'Slug is already taken\.'/);
});

test('look editor maps duplicate-product persistence conflicts separately from slug errors', () => {
  assert.match(pageSource, /Product is already included in this Look/);
  assert.match(pageSource, /return t\('looks\.duplicateProduct'\)/);
});

test('look edit slug updates use the same clean conflict handling as creates', () => {
  assert.match(pageSource, /mode === 'edit' && lookId/);
  assert.match(pageSource, /api\.looks\.update\(lookId, payload\)/);
  assert.match(pageSource, /api\.looks\.create\(payload\)/);
  assert.match(pageSource, /formatLookRequestError\(requestError, t\)/);
});

test('look editor supports product components and hidden product badges', () => {
  assert.match(pageSource, /api\.products\.listAdmin/);
  assert.match(pageSource, /addProductToLook/);
  assert.match(pageSource, /duplicateProduct/);
  assert.match(pageSource, /isDefaultSelected/);
  assert.match(pageSource, /hasMultipleActiveColors/);
  assert.match(pageSource, /formatProductSizeGroup/);
  assert.match(pageSource, /productEditor\.sizeGroup/);
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
