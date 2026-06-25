import React from 'react';
import { trackTelemetry } from '../telemetry';

const CHUNK_RELOAD_STORAGE_PREFIX = 'telegram_shop_chunk_reload';

type ChunkLoadRecoveryProps = {
  children: React.ReactNode;
  resetKey: string;
  appVersion?: string;
  reloadWindow?: () => void;
};

type ChunkLoadRecoveryState = {
  error: Error | null;
  chunkLoadFailed: boolean;
};

function errorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error ?? '');
}

export function isChunkLoadError(error: unknown) {
  const message = errorMessage(error).toLowerCase();
  const name = error instanceof Error ? error.name.toLowerCase() : '';

  return name === 'chunkloaderror'
    || message.includes('failed to fetch dynamically imported module')
    || message.includes('error loading dynamically imported module')
    || message.includes('importing a module script failed')
    || message.includes('loading chunk')
    || message.includes('chunk load failed');
}

function chunkReloadStorageKey(appVersion: string) {
  return `${CHUNK_RELOAD_STORAGE_PREFIX}:${appVersion}`;
}

export function maybeReloadAfterChunkLoadError({
  appVersion,
  error,
  reloadWindow = () => window.location.reload(),
  storage = window.sessionStorage,
}: {
  appVersion: string;
  error: unknown;
  reloadWindow?: () => void;
  storage?: Storage;
}) {
  if (!isChunkLoadError(error)) {
    return false;
  }

  const storageKey = chunkReloadStorageKey(appVersion);
  if (storage.getItem(storageKey) === '1') {
    trackTelemetry('chunk.recovery_failed', {
      route: window.location.pathname,
      error_category: 'chunk_load_failed',
      app_version: appVersion,
      success: false,
    }, { priority: 'critical' });
    return false;
  }

  storage.setItem(storageKey, '1');
  trackTelemetry('chunk.reload_attempted', {
    route: window.location.pathname,
    error_category: 'chunk_load_failed',
    app_version: appVersion,
  }, { priority: 'critical' });
  reloadWindow();
  return true;
}

export class ChunkLoadRecovery extends React.Component<
  ChunkLoadRecoveryProps,
  ChunkLoadRecoveryState
> {
  state: ChunkLoadRecoveryState = {
    error: null,
    chunkLoadFailed: false,
  };

  static getDerivedStateFromError(error: Error): ChunkLoadRecoveryState {
    return {
      error,
      chunkLoadFailed: isChunkLoadError(error),
    };
  }

  componentDidCatch(error: Error) {
    if (isChunkLoadError(error)) {
      trackTelemetry('chunk.load_failed', {
        route: window.location.pathname,
        error_category: 'chunk_load_failed',
        app_version: this.props.appVersion ?? __APP_VERSION__,
        success: false,
      }, { priority: 'critical' });
    }
    maybeReloadAfterChunkLoadError({
      appVersion: this.props.appVersion ?? __APP_VERSION__,
      error,
      reloadWindow: this.props.reloadWindow,
    });
  }

  componentDidUpdate(previousProps: ChunkLoadRecoveryProps) {
    if (previousProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null, chunkLoadFailed: false });
    }
  }

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    if (this.state.chunkLoadFailed) {
      return (
        <section className="route-error-state" role="alert">
          <h2>Не удалось загрузить обновление</h2>
          <p>
            Похоже, приложение обновилось, пока Mini App был открыт. Мы уже попробовали
            перезагрузить его один раз. Нажмите кнопку, чтобы повторить безопасно.
          </p>
          <button className="primary-button" type="button" onClick={this.props.reloadWindow ?? (() => window.location.reload())}>
            Повторить загрузку
          </button>
        </section>
      );
    }

    return (
      <section className="route-error-state" role="alert">
        <h2>Что-то пошло не так</h2>
        <p>Маршрут не загрузился. Попробуйте открыть страницу ещё раз.</p>
        <button className="secondary-button" type="button" onClick={this.props.reloadWindow ?? (() => window.location.reload())}>
          Обновить
        </button>
      </section>
    );
  }
}
