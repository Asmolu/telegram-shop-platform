export const SELLER_IDLE_TIMEOUT_MS = 15 * 60 * 1000;
export const SELLER_ACTIVITY_THROTTLE_MS = 5 * 1000;
export const SELLER_SESSION_HANDOFF_WAIT_MS = 250;

const ACTIVITY_STORAGE_KEY = 'seller_panel_last_activity_at';
const AUTH_EPOCH_STORAGE_KEY = 'seller_panel_auth_epoch';
const LOGOUT_STORAGE_KEY = 'seller_panel_logout_event';
const CHANNEL_NAME = 'seller_panel_auth';

export type SellerLogoutReason = 'idle' | 'manual' | 'unauthorized';

interface SessionMessageBase {
  sourceId: string;
}

type SessionMessage =
  | (SessionMessageBase & { type: 'activity'; at: number; epoch: string | null })
  | (SessionMessageBase & {
      type: 'logout';
      epoch: string | null;
      reason: SellerLogoutReason;
    })
  | (SessionMessageBase & { type: 'token-request'; requestId: string })
  | (SessionMessageBase & {
      type: 'token-response';
      requestId: string;
      token: string;
      epoch: string;
      lastActivityAt: number;
    });

interface StorageEventLike {
  key: string | null;
  newValue: string | null;
}

interface SessionChannel {
  onmessage: ((event: MessageEvent) => void) | null;
  postMessage(message: SessionMessage): void;
  close(): void;
}

interface SellerSessionEnvironment {
  sharedStorage: Storage;
  now(): number;
  randomId(): string;
  setTimeout(callback: () => void, delay: number): number;
  clearTimeout(timerId: number): void;
  addWindowListener(type: string, listener: EventListener, options?: AddEventListenerOptions): void;
  removeWindowListener(type: string, listener: EventListener, options?: EventListenerOptions): void;
  createChannel(): SessionChannel | null;
}

export interface SellerTokenStore {
  getToken(): string | null;
  getScope(): 'local' | 'session' | null;
  setSessionToken(token: string): void;
  clear(): void;
}

interface SellerSessionCoordinatorOptions {
  onTokenReceived(token: string): void;
  onLogout(reason: SellerLogoutReason): void;
  environment?: SellerSessionEnvironment;
  tokenStore: SellerTokenStore;
}

export function calculateIdleDeadline(lastActivityAt: number): number {
  return lastActivityAt + SELLER_IDLE_TIMEOUT_MS;
}

export function isIdleExpired(lastActivityAt: number, now: number): boolean {
  return now >= calculateIdleDeadline(lastActivityAt);
}

export class SellerSessionCoordinator {
  private readonly environment: SellerSessionEnvironment;
  private readonly onTokenReceived: (token: string) => void;
  private readonly onLogout: (reason: SellerLogoutReason) => void;
  private readonly tokenStore: SellerTokenStore;
  private readonly sourceId: string;
  private channel: SessionChannel | null = null;
  private idleTimerId: number | null = null;
  private lastActivityAt = 0;
  private lastPublishedActivityAt = 0;
  private authGeneration = 0;
  private authEpoch: string | null = null;
  private pendingTokenRequestId: string | null = null;
  private started = false;

  constructor(options: SellerSessionCoordinatorOptions) {
    this.environment = options.environment ?? createBrowserEnvironment();
    this.onTokenReceived = options.onTokenReceived;
    this.onLogout = options.onLogout;
    this.tokenStore = options.tokenStore;
    this.sourceId = this.environment.randomId();
  }

  start(): void {
    if (this.started) return;
    this.started = true;
    this.channel = this.environment.createChannel();
    if (this.channel) {
      this.channel.onmessage = (event) => this.handleChannelMessage(event.data);
    }

    meaningfulActivityEvents.forEach(({ type, options }) => {
      this.environment.addWindowListener(type, this.handleActivity, options);
    });
    this.environment.addWindowListener('storage', this.handleStorage);

    if (this.tokenStore.getToken()) {
      this.beginExistingSession();
    } else {
      this.requestSessionToken();
    }
  }

  stop(): void {
    if (!this.started) return;
    this.started = false;
    meaningfulActivityEvents.forEach(({ type, options }) => {
      this.environment.removeWindowListener(type, this.handleActivity, options);
    });
    this.environment.removeWindowListener('storage', this.handleStorage);
    this.clearIdleTimer();
    this.channel?.close();
    this.channel = null;
  }

  authenticated(): void {
    if (!this.tokenStore.getToken()) return;
    this.authGeneration += 1;
    this.clearIdleTimer();
    this.lastActivityAt = 0;
    this.lastPublishedActivityAt = 0;
    this.authEpoch = `${this.environment.now()}:${this.environment.randomId()}`;
    this.environment.sharedStorage.setItem(AUTH_EPOCH_STORAGE_KEY, this.authEpoch);
    this.recordActivity(this.environment.now(), true);
  }

  logout(reason: SellerLogoutReason): void {
    if (!this.tokenStore.getToken() && !this.authEpoch) return;
    const epoch = this.authEpoch;
    this.clearAuthentication();
    this.channel?.postMessage({ type: 'logout', sourceId: this.sourceId, epoch, reason });
    this.environment.sharedStorage.setItem(LOGOUT_STORAGE_KEY, JSON.stringify({ at: this.environment.now(), epoch, reason }));
    this.onLogout(reason);
  }

  private beginExistingSession(): void {
    this.authGeneration += 1;
    this.authEpoch = this.environment.sharedStorage.getItem(AUTH_EPOCH_STORAGE_KEY);
    if (!this.authEpoch) {
      this.authEpoch = `${this.environment.now()}:${this.environment.randomId()}`;
      this.environment.sharedStorage.setItem(AUTH_EPOCH_STORAGE_KEY, this.authEpoch);
    }

    const sharedActivityAt = readStoredTimestamp(this.environment.sharedStorage, ACTIVITY_STORAGE_KEY);
    if (sharedActivityAt && isIdleExpired(sharedActivityAt, this.environment.now())) {
      this.logout('idle');
      return;
    }

    if (sharedActivityAt) {
      this.acceptActivity(sharedActivityAt);
    } else {
      this.recordActivity(this.environment.now(), true);
    }
  }

  private requestSessionToken(): void {
    if (!this.channel) return;
    this.pendingTokenRequestId = `${this.sourceId}:${this.environment.randomId()}`;
    this.channel.postMessage({
      type: 'token-request',
      sourceId: this.sourceId,
      requestId: this.pendingTokenRequestId,
    });
  }

  private readonly handleActivity = (): void => {
    if (!this.tokenStore.getToken()) return;
    const now = this.environment.now();
    this.refreshSharedActivity();
    if (this.lastActivityAt && isIdleExpired(this.lastActivityAt, now)) {
      this.logout('idle');
      return;
    }
    this.recordActivity(now, false);
  };

  private readonly handleStorage = (event: Event): void => {
    const storageEvent = event as Event & StorageEventLike;
    if (storageEvent.key === ACTIVITY_STORAGE_KEY && storageEvent.newValue) {
      const at = Number(storageEvent.newValue);
      if (Number.isFinite(at)) this.acceptActivity(at);
      return;
    }

    if (storageEvent.key === AUTH_EPOCH_STORAGE_KEY && storageEvent.newValue) {
      if (this.tokenStore.getToken()) this.authEpoch = storageEvent.newValue;
      return;
    }

    if (storageEvent.key === LOGOUT_STORAGE_KEY && storageEvent.newValue) {
      const logout = parseLogoutEvent(storageEvent.newValue);
      if (logout && this.shouldAcceptLogout(logout.epoch)) {
        this.receiveLogout(logout.reason);
      }
    }
  };

  private handleChannelMessage(value: unknown): void {
    if (!isSessionMessage(value) || value.sourceId === this.sourceId) return;

    if (value.type === 'activity') {
      if (value.epoch && value.at >= this.lastActivityAt) this.authEpoch = value.epoch;
      this.acceptActivity(value.at);
      return;
    }

    if (value.type === 'logout') {
      if (this.shouldAcceptLogout(value.epoch)) this.receiveLogout(value.reason);
      return;
    }

    if (value.type === 'token-request') {
      const token = this.tokenStore.getToken();
      if (!token || this.tokenStore.getScope() !== 'session' || !this.authEpoch) return;
      const now = this.environment.now();
      if (!this.lastActivityAt || isIdleExpired(this.lastActivityAt, now)) {
        this.logout('idle');
        return;
      }
      this.channel?.postMessage({
        type: 'token-response',
        sourceId: this.sourceId,
        requestId: value.requestId,
        token,
        epoch: this.authEpoch,
        lastActivityAt: this.lastActivityAt,
      });
      return;
    }

    if (
      value.type === 'token-response' &&
      value.requestId === this.pendingTokenRequestId &&
      !this.tokenStore.getToken() &&
      !isIdleExpired(value.lastActivityAt, this.environment.now())
    ) {
      this.pendingTokenRequestId = null;
      this.tokenStore.setSessionToken(value.token);
      this.authGeneration += 1;
      this.authEpoch = value.epoch;
      this.environment.sharedStorage.setItem(AUTH_EPOCH_STORAGE_KEY, value.epoch);
      this.acceptActivity(value.lastActivityAt);
      this.onTokenReceived(value.token);
    }
  }

  private recordActivity(at: number, forcePublish: boolean): void {
    this.acceptActivity(at);
    if (!forcePublish && at - this.lastPublishedActivityAt < SELLER_ACTIVITY_THROTTLE_MS) {
      return;
    }
    this.lastPublishedActivityAt = at;
    this.environment.sharedStorage.setItem(ACTIVITY_STORAGE_KEY, String(at));
    this.channel?.postMessage({
      type: 'activity',
      sourceId: this.sourceId,
      at,
      epoch: this.authEpoch,
    });
  }

  private acceptActivity(at: number): void {
    if (!this.tokenStore.getToken() || at <= this.lastActivityAt) return;
    this.lastActivityAt = at;
    this.scheduleIdleTimer();
  }

  private scheduleIdleTimer(): void {
    this.clearIdleTimer();
    const generation = this.authGeneration;
    const delay = Math.max(0, calculateIdleDeadline(this.lastActivityAt) - this.environment.now());
    this.idleTimerId = this.environment.setTimeout(() => {
      this.idleTimerId = null;
      if (generation !== this.authGeneration || !this.tokenStore.getToken()) return;
      const previousActivityAt = this.lastActivityAt;
      this.refreshSharedActivity();
      if (this.lastActivityAt > previousActivityAt) return;
      if (isIdleExpired(this.lastActivityAt, this.environment.now())) {
        this.logout('idle');
      } else {
        this.scheduleIdleTimer();
      }
    }, delay);
  }

  private clearIdleTimer(): void {
    if (this.idleTimerId === null) return;
    this.environment.clearTimeout(this.idleTimerId);
    this.idleTimerId = null;
  }

  private refreshSharedActivity(): void {
    const sharedActivityAt = readStoredTimestamp(
      this.environment.sharedStorage,
      ACTIVITY_STORAGE_KEY,
    );
    if (sharedActivityAt) this.acceptActivity(sharedActivityAt);
  }

  private shouldAcceptLogout(epoch: string | null): boolean {
    return Boolean(this.tokenStore.getToken() || this.authEpoch) && (
      !epoch || !this.authEpoch || epoch === this.authEpoch
    );
  }

  private receiveLogout(reason: SellerLogoutReason): void {
    this.clearAuthentication();
    this.onLogout(reason);
  }

  private clearAuthentication(): void {
    this.authGeneration += 1;
    this.clearIdleTimer();
    this.tokenStore.clear();
    this.environment.sharedStorage.removeItem(ACTIVITY_STORAGE_KEY);
    this.environment.sharedStorage.removeItem(AUTH_EPOCH_STORAGE_KEY);
    this.lastActivityAt = 0;
    this.lastPublishedActivityAt = 0;
    this.authEpoch = null;
    this.pendingTokenRequestId = null;
  }
}

const meaningfulActivityEvents: Array<{ type: string; options?: AddEventListenerOptions }> = [
  { type: 'pointerdown', options: { passive: true } },
  { type: 'keydown' },
  { type: 'touchstart', options: { passive: true } },
  { type: 'scroll', options: { passive: true } },
  { type: 'focus' },
];

function createBrowserEnvironment(): SellerSessionEnvironment {
  return {
    sharedStorage: localStorage,
    now: () => Date.now(),
    randomId: () => crypto.randomUUID(),
    setTimeout: (callback, delay) => window.setTimeout(callback, delay),
    clearTimeout: (timerId) => window.clearTimeout(timerId),
    addWindowListener: (type, listener, options) => window.addEventListener(type, listener, options),
    removeWindowListener: (type, listener, options) => window.removeEventListener(type, listener, options),
    createChannel: () =>
      typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(CHANNEL_NAME),
  };
}

function readStoredTimestamp(storage: Storage, key: string): number | null {
  const value = Number(storage.getItem(key));
  return Number.isFinite(value) && value > 0 ? value : null;
}


function parseLogoutEvent(value: string): { epoch: string | null; reason: SellerLogoutReason } | null {
  try {
    const parsed = JSON.parse(value) as { epoch?: unknown; reason?: unknown };
    if (!isLogoutReason(parsed.reason)) return null;
    return { epoch: typeof parsed.epoch === 'string' ? parsed.epoch : null, reason: parsed.reason };
  } catch {
    return null;
  }
}

function isSessionMessage(value: unknown): value is SessionMessage {
  if (!value || typeof value !== 'object') return false;
  const message = value as Record<string, unknown>;
  if (typeof message.sourceId !== 'string') return false;
  if (message.type === 'activity') {
    return Number.isFinite(message.at) && (
      message.epoch === null || typeof message.epoch === 'string'
    );
  }
  if (message.type === 'logout') {
    return isLogoutReason(message.reason) && (
      message.epoch === null || typeof message.epoch === 'string'
    );
  }
  if (message.type === 'token-request') return typeof message.requestId === 'string';
  if (message.type === 'token-response') {
    return (
      typeof message.requestId === 'string' &&
      typeof message.token === 'string' &&
      typeof message.epoch === 'string' &&
      Number.isFinite(message.lastActivityAt)
    );
  }
  return false;
}

function isLogoutReason(value: unknown): value is SellerLogoutReason {
  return value === 'idle' || value === 'manual' || value === 'unauthorized';
}
