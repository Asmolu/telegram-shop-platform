import { afterEach, describe, expect, it, vi } from 'vitest';
import { initTelegramApp, type TelegramWebApp } from './webApp';

describe('Telegram WebApp viewport lifecycle', () => {
  afterEach(() => {
    delete window.Telegram;
    vi.restoreAllMocks();
  });

  it('removes Telegram viewport and window listeners during cleanup', () => {
    const webApp: TelegramWebApp = {
      initData: '',
      platform: 'android',
      isFullscreen: true,
      ready: vi.fn(),
      expand: vi.fn(),
      disableVerticalSwipes: vi.fn(),
      requestFullscreen: vi.fn(),
      onEvent: vi.fn(),
      offEvent: vi.fn(),
    };
    window.Telegram = { WebApp: webApp };
    const addEventListenerSpy = vi.spyOn(window, 'addEventListener');
    const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');

    const cleanup = initTelegramApp();
    cleanup();

    expect(webApp.onEvent).toHaveBeenCalledWith('viewportChanged', expect.any(Function));
    expect(webApp.onEvent).toHaveBeenCalledWith('fullscreenChanged', expect.any(Function));
    expect(webApp.offEvent).toHaveBeenCalledWith('viewportChanged', expect.any(Function));
    expect(webApp.offEvent).toHaveBeenCalledWith('fullscreenChanged', expect.any(Function));
    expect(addEventListenerSpy).toHaveBeenCalledWith('resize', expect.any(Function));
    expect(removeEventListenerSpy).toHaveBeenCalledWith('resize', expect.any(Function));
  });
});
