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
