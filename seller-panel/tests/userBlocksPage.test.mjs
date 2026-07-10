import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/shared/api/client.ts', import.meta.url), 'utf8');
const typesSource = readFileSync(new URL('../src/shared/api/types.ts', import.meta.url), 'utf8');
const i18nSource = readFileSync(new URL('../src/shared/i18n/index.tsx', import.meta.url), 'utf8');
const pageSource = readFileSync(
  new URL('../src/pages/UserBlocks/UserBlocksPage.tsx', import.meta.url),
  'utf8',
);

test('/blocks route and sidebar label are wired', () => {
  assert.match(appSource, /\/blocks/);
  assert.match(appSource, /\/user-blocks/);
  assert.match(appSource, /nav\.userBlocks/);
  assert.match(appSource, /UserBlocksPage/);
  assert.match(i18nSource, /'nav\.userBlocks': '\\u0411\\u043b\\u043e\\u043a/);
});

test('seller API exposes user block endpoints', () => {
  assert.match(apiSource, /userBlocks: \{/);
  assert.match(apiSource, /\/users\/admin\/blocks/);
  assert.match(apiSource, /\/users\/admin\/blocks\/\$\{blockId\}\/unblock/);
  assert.match(typesSource, /export interface UserBlock/);
  assert.match(typesSource, /telegram_id: number \| null/);
  assert.match(typesSource, /telegram_username: string \| null/);
  assert.match(typesSource, /blocked_by_user_id: number \| null/);
  assert.match(typesSource, /export interface UserBlockPayload/);
});

test('user blocks page submits by id username and optional reason', () => {
  assert.match(pageSource, /api\.userBlocks\.create/);
  assert.match(pageSource, /telegram_id: idValue \? Number\(idValue\) : null/);
  assert.match(pageSource, /telegram_username: usernameValue \|\| null/);
  assert.match(pageSource, /reason: reason\.trim\(\) \|\| null/);
  assert.match(pageSource, /normalizeUsernameInput/);
  assert.match(pageSource, /blocks\.validation\.identifierRequired/);
  assert.match(pageSource, /blocks\.validation\.telegramId/);
});

test('user blocks page renders active list and unblock action', () => {
  assert.match(pageSource, /api\.userBlocks\.list/);
  assert.match(pageSource, /api\.userBlocks\.unblock/);
  assert.match(pageSource, /activeBlocks/);
  assert.match(pageSource, /block\.telegram_id/);
  assert.match(pageSource, /block\.telegram_username/);
  assert.match(pageSource, /block\.reason/);
  assert.match(pageSource, /formatActor/);
  assert.match(pageSource, /formatDate\(block\.blocked_at/);
  assert.match(pageSource, /blocks\.unblock/);
});
