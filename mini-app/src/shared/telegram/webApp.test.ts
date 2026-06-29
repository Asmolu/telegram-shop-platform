import { afterEach, describe, expect, it, vi } from 'vitest';
import { initTelegramApp, syncTelegramBackButton, type TelegramWebApp } from './webApp';

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

  it('shows, binds, unbinds, and hides Telegram BackButton', () => {
    const onClick = vi.fn();
    const backButton = {
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn(),
      offClick: vi.fn(),
    };
    const webApp: TelegramWebApp = {
      initData: '',
      BackButton: backButton,
    };
    window.Telegram = { WebApp: webApp };

    const cleanup = syncTelegramBackButton(true, onClick);

    expect(backButton.show).toHaveBeenCalledTimes(1);
    expect(backButton.onClick).toHaveBeenCalledWith(onClick);

    cleanup();

    expect(backButton.offClick).toHaveBeenCalledWith(onClick);
    expect(backButton.hide).toHaveBeenCalledTimes(1);
  });

  it('hides Telegram BackButton without binding when hidden', () => {
    const backButton = {
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn(),
      offClick: vi.fn(),
    };
    window.Telegram = {
      WebApp: {
        initData: '',
        BackButton: backButton,
      },
    };

    syncTelegramBackButton(false, vi.fn());

    expect(backButton.hide).toHaveBeenCalledTimes(1);
    expect(backButton.show).not.toHaveBeenCalled();
    expect(backButton.onClick).not.toHaveBeenCalled();
  });
});
