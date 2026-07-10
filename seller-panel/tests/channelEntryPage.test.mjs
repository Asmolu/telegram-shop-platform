import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/shared/api/client.ts', import.meta.url), 'utf8');
const pageSource = readFileSync(
  new URL('../src/pages/ChannelEntry/ChannelEntryPage.tsx', import.meta.url),
  'utf8',
);

test('/channel-entry route and sidebar label are wired', () => {
  assert.match(appSource, /\/channel-entry/);
  assert.match(appSource, /nav\.channelEntry/);
  assert.match(pageSource, /Вход из Telegram-канала/);
});

test('channel entry page shows generated direct link and manual channel helper text', () => {
  assert.match(pageSource, /Mini App direct link/);
  assert.match(pageSource, /@checktsplatform/);
  assert.match(pageSource, /Публичную ссылку можно найти/);
  assert.match(pageSource, /Закрепить снова/);
});

test('channel entry submit uses backend API without exposing bot token or editable button URL', () => {
  assert.match(apiSource, /channelEntry/);
  assert.match(apiSource, /\/channel-entry\/publish/);
  assert.doesNotMatch(pageSource, /TELEGRAM_CUSTOMER_BOT_TOKEN/);
  assert.doesNotMatch(pageSource, /button_url:\s*currentPreview/);
});

test('button style selector exposes only supported Telegram styles', () => {
  assert.match(pageSource, /BUTTON_STYLE_OPTIONS/);
  assert.match(pageSource, /value: 'default'.*По умолчанию/);
  assert.match(pageSource, /value: 'primary'.*Основная/);
  assert.match(pageSource, /value: 'success'.*Успешная/);
  assert.match(pageSource, /value: 'danger'.*Важная/);
  assert.doesNotMatch(pageSource, /value: 'secondary'/);
});

test('photo upload renders thumbnails and supports removal', () => {
  assert.match(apiSource, /uploadPhoto/);
  assert.match(pageSource, /accept="image\/jpeg,image\/png,image\/webp"/);
  assert.match(pageSource, /channel-entry-photo-list/);
  assert.match(pageSource, /removePhoto\(photo\.file_path\)/);
  assert.match(pageSource, /Удалить фото/);
});

test('photo selection enforces a maximum of four', () => {
  assert.match(pageSource, /MAX_CHANNEL_ENTRY_PHOTOS = 4/);
  assert.match(pageSource, /selectedPhotos\.length \+ incomingFiles\.length/);
  assert.match(pageSource, /Можно прикрепить не больше/);
});

test('publish payload includes style and selected photo paths', () => {
  assert.match(pageSource, /button_style: publishForm\.buttonStyle/);
  assert.match(pageSource, /photo_paths: selectedPhotos\.map/);
  assert.match(pageSource, /api\.channelEntry\.publish/);
});

test('preview card displays photos, text, button, and approximate style', () => {
  assert.match(pageSource, /channel-entry-preview-photos/);
  assert.match(pageSource, /currentPreview\.text/);
  assert.match(pageSource, /currentPreview\.button_text/);
  assert.match(pageSource, /telegram-button-preview-\$\{currentPreview\.button_style\}/);
  assert.match(pageSource, /Стиль: \{selectedStyleLabel\}/);
});

test('publish success clears selected photos and refreshes history', () => {
  assert.match(pageSource, /setActionMessage\(response\.message\)/);
  assert.match(pageSource, /setSelectedPhotos\(\[\]\)/);
  assert.match(pageSource, /loadHistory\(\)/);
});

test('API errors are rendered in the channel-entry action state', () => {
  assert.match(pageSource, /requestError instanceof ApiError/);
  assert.match(pageSource, /setActionError/);
  assert.match(pageSource, /form-error/);
});
