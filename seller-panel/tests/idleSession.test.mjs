import assert from 'node:assert/strict';
import test from 'node:test';

import { notifyUnauthorized, subscribeToUnauthorized } from '../src/shared/auth/authEvents.ts';
import {
  SELLER_IDLE_TIMEOUT_MS,
  SellerSessionCoordinator,
  calculateIdleDeadline,
  isIdleExpired,
} from '../src/shared/auth/idleSession.ts';
import {
  getStoredToken,
  getTokenStorageScope,
  setStoredToken,
} from '../src/shared/auth/tokenStorage.ts';

const LOCAL_TOKEN_KEY = 'seller_panel_access_token';
const SESSION_TOKEN_KEY = 'seller_panel_session_access_token';
let tabSequence = 0;

class MemoryStorage {
  #values = new Map();

  get length() { return this.#values.size; }
  clear() { this.#values.clear(); }
  getItem(key) { return this.#values.get(key) ?? null; }
  key(index) { return [...this.#values.keys()][index] ?? null; }
  removeItem(key) { this.#values.delete(key); }
  setItem(key, value) { this.#values.set(key, String(value)); }
}

class FakeClock {
  now = 1_000;
  #nextTimerId = 1;
  #timers = new Map();

  setTimeout = (callback, delay) => {
    const id = this.#nextTimerId++;
    this.#timers.set(id, { at: this.now + delay, callback });
    return id;
  };

  clearTimeout = (id) => this.#timers.delete(id);

  advance(milliseconds) {
    const target = this.now + milliseconds;
    while (true) {
      const next = [...this.#timers.entries()]
        .filter(([, timer]) => timer.at <= target)
        .sort((left, right) => left[1].at - right[1].at)[0];
      if (!next) break;
      const [id, timer] = next;
      this.#timers.delete(id);
      this.now = timer.at;
      timer.callback();
    }
    this.now = target;
  }
}

class FakeWindow {
  #listeners = new Map();

  add = (type, listener) => {
    const listeners = this.#listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.#listeners.set(type, listeners);
  };

  remove = (type, listener) => this.#listeners.get(type)?.delete(listener);

  dispatch(type, event = {}) {
    this.#listeners.get(type)?.forEach((listener) => listener(event));
  }
}

class BroadcastHub {
  #channels = new Set();

  create() {
    const channel = {
      onmessage: null,
      postMessage: (message) => {
        this.#channels.forEach((peer) => {
          if (peer !== channel) peer.onmessage?.({ data: message });
        });
      },
      close: () => this.#channels.delete(channel),
    };
    this.#channels.add(channel);
    return channel;
  }
}

function createTab({ clock, hub, sharedStorage, token = null, scope = 'session' }) {
  const sessionStorage = new MemoryStorage();
  const fakeWindow = new FakeWindow();
  const logoutReasons = [];
  const receivedTokens = [];
  let sequence = 0;
  const tabId = ++tabSequence;

  if (token) {
    (scope === 'local' ? sharedStorage : sessionStorage).setItem(
      scope === 'local' ? LOCAL_TOKEN_KEY : SESSION_TOKEN_KEY,
      token,
    );
  }

  const tokenStore = {
    getToken: () => sharedStorage.getItem(LOCAL_TOKEN_KEY) ?? sessionStorage.getItem(SESSION_TOKEN_KEY),
    getScope: () => sharedStorage.getItem(LOCAL_TOKEN_KEY)
      ? 'local'
      : sessionStorage.getItem(SESSION_TOKEN_KEY) ? 'session' : null,
    setSessionToken: (nextToken) => {
      sharedStorage.removeItem(LOCAL_TOKEN_KEY);
      sessionStorage.setItem(SESSION_TOKEN_KEY, nextToken);
    },
    clear: () => {
      sharedStorage.removeItem(LOCAL_TOKEN_KEY);
      sessionStorage.removeItem(SESSION_TOKEN_KEY);
    },
  };

  const coordinator = new SellerSessionCoordinator({
    tokenStore,
    environment: {
      sharedStorage,
      now: () => clock.now,
      randomId: () => `tab-${tabId}-id-${++sequence}`,
      setTimeout: clock.setTimeout,
      clearTimeout: clock.clearTimeout,
      addWindowListener: fakeWindow.add,
      removeWindowListener: fakeWindow.remove,
      createChannel: () => hub.create(),
    },
    onTokenReceived: (receivedToken) => receivedTokens.push(receivedToken),
    onLogout: (reason) => logoutReasons.push(reason),
  });

  return { coordinator, fakeWindow, logoutReasons, receivedTokens, sessionStorage, tokenStore };
}

function setup(token = 'session-token', scope = 'session') {
  const clock = new FakeClock();
  const hub = new BroadcastHub();
  const sharedStorage = new MemoryStorage();
  return { clock, hub, sharedStorage, tab: createTab({ clock, hub, sharedStorage, token, scope }) };
}

test('session remains active before 15 minutes and expires at the deadline', () => {
  const { clock, tab } = setup();
  tab.coordinator.start();

  assert.equal(calculateIdleDeadline(clock.now), clock.now + SELLER_IDLE_TIMEOUT_MS);
  assert.equal(isIdleExpired(clock.now, clock.now + SELLER_IDLE_TIMEOUT_MS - 1), false);
  clock.advance(SELLER_IDLE_TIMEOUT_MS - 1);
  assert.equal(tab.tokenStore.getToken(), 'session-token');
  assert.deepEqual(tab.logoutReasons, []);

  clock.advance(1);
  assert.equal(tab.tokenStore.getToken(), null);
  assert.deepEqual(tab.logoutReasons, ['idle']);
});

test('meaningful activity resets the idle timer', () => {
  const { clock, tab } = setup();
  tab.coordinator.start();
  clock.advance(10 * 60 * 1000);
  tab.fakeWindow.dispatch('pointerdown');
  clock.advance(SELLER_IDLE_TIMEOUT_MS - 1);

  assert.equal(tab.tokenStore.getToken(), 'session-token');
  clock.advance(1);
  assert.deepEqual(tab.logoutReasons, ['idle']);
});

test('activity from another tab resets the shared deadline', () => {
  const clock = new FakeClock();
  const hub = new BroadcastHub();
  const sharedStorage = new MemoryStorage();
  const first = createTab({ clock, hub, sharedStorage, token: 'local-token', scope: 'local' });
  const second = createTab({ clock, hub, sharedStorage });
  first.coordinator.start();
  second.coordinator.start();
  clock.advance(10 * 60 * 1000);
  first.fakeWindow.dispatch('scroll');
  clock.advance(10 * 60 * 1000);

  assert.deepEqual(first.logoutReasons, []);
  assert.deepEqual(second.logoutReasons, []);
  assert.equal(second.tokenStore.getToken(), 'local-token');
});

test('manual logout is broadcast to every tab', () => {
  const clock = new FakeClock();
  const hub = new BroadcastHub();
  const sharedStorage = new MemoryStorage();
  const first = createTab({ clock, hub, sharedStorage, token: 'session-token' });
  const second = createTab({ clock, hub, sharedStorage });
  first.coordinator.start();
  second.coordinator.start();
  first.coordinator.logout('manual');

  assert.deepEqual(first.logoutReasons, ['manual']);
  assert.deepEqual(second.logoutReasons, ['manual']);
  assert.equal(second.tokenStore.getToken(), null);
});

test('idle logout reaches every authenticated tab', () => {
  const clock = new FakeClock();
  const hub = new BroadcastHub();
  const sharedStorage = new MemoryStorage();
  const first = createTab({ clock, hub, sharedStorage, token: 'session-token' });
  const second = createTab({ clock, hub, sharedStorage });
  first.coordinator.start();
  second.coordinator.start();
  clock.advance(SELLER_IDLE_TIMEOUT_MS);

  assert.deepEqual(first.logoutReasons, ['idle']);
  assert.deepEqual(second.logoutReasons, ['idle']);
  assert.equal(first.tokenStore.getToken(), null);
  assert.equal(second.tokenStore.getToken(), null);
});

test('a stale timer cannot log out a newly authenticated session', () => {
  const { clock, tab } = setup('old-token');
  tab.coordinator.start();
  clock.advance(10 * 60 * 1000);
  tab.tokenStore.setSessionToken('new-token');
  tab.coordinator.authenticated();
  clock.advance(5 * 60 * 1000);

  assert.equal(tab.tokenStore.getToken(), 'new-token');
  assert.deepEqual(tab.logoutReasons, []);
  clock.advance(10 * 60 * 1000);
  assert.deepEqual(tab.logoutReasons, ['idle']);
});

test('session token handoff stays in the receiving tab session storage', () => {
  const clock = new FakeClock();
  const hub = new BroadcastHub();
  const sharedStorage = new MemoryStorage();
  const first = createTab({ clock, hub, sharedStorage, token: 'session-token' });
  const second = createTab({ clock, hub, sharedStorage });
  first.coordinator.start();
  second.coordinator.start();

  assert.deepEqual(second.receivedTokens, ['session-token']);
  assert.equal(second.sessionStorage.getItem(SESSION_TOKEN_KEY), 'session-token');
  assert.equal(sharedStorage.getItem(LOCAL_TOKEN_KEY), null);
});

test('local and session token scopes remain distinct', () => {
  const sharedStorage = new MemoryStorage();
  const clock = new FakeClock();
  const hub = new BroadcastHub();
  const localTab = createTab({ clock, hub, sharedStorage, token: 'local-token', scope: 'local' });
  assert.equal(localTab.tokenStore.getScope(), 'local');
  assert.equal(sharedStorage.getItem(LOCAL_TOKEN_KEY), 'local-token');
  assert.equal(localTab.sessionStorage.getItem(SESSION_TOKEN_KEY), null);

  localTab.tokenStore.setSessionToken('session-token');
  assert.equal(localTab.tokenStore.getScope(), 'session');
  assert.equal(sharedStorage.getItem(LOCAL_TOKEN_KEY), null);
  assert.equal(localTab.sessionStorage.getItem(SESSION_TOKEN_KEY), 'session-token');
});

test('browser token storage preserves local and session persistence semantics', () => {
  const originalLocalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const originalSessionStorage = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage');
  const localStorage = new MemoryStorage();
  const sessionStorage = new MemoryStorage();
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: localStorage });
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: sessionStorage });

  try {
    setStoredToken('local-token', 'local');
    assert.equal(getStoredToken(), 'local-token');
    assert.equal(getTokenStorageScope(), 'local');
    assert.equal(sessionStorage.getItem(SESSION_TOKEN_KEY), null);

    setStoredToken('session-token', 'session');
    assert.equal(getStoredToken(), 'session-token');
    assert.equal(getTokenStorageScope(), 'session');
    assert.equal(localStorage.getItem(LOCAL_TOKEN_KEY), null);
  } finally {
    if (originalLocalStorage) Object.defineProperty(globalThis, 'localStorage', originalLocalStorage);
    else delete globalThis.localStorage;
    if (originalSessionStorage) Object.defineProperty(globalThis, 'sessionStorage', originalSessionStorage);
    else delete globalThis.sessionStorage;
  }
});

test('API 401 notification clears authentication safely across tabs', () => {
  const { tab } = setup();
  tab.coordinator.start();
  const unsubscribe = subscribeToUnauthorized(() => tab.coordinator.logout('unauthorized'));
  notifyUnauthorized();
  unsubscribe();

  assert.equal(tab.tokenStore.getToken(), null);
  assert.deepEqual(tab.logoutReasons, ['unauthorized']);
});
