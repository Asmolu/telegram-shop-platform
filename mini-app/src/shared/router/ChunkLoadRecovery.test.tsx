import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ChunkLoadRecovery,
  isChunkLoadError,
  maybeReloadAfterChunkLoadError,
} from './ChunkLoadRecovery';
import { clearStoredAccessToken, getStoredAccessToken, storeAccessToken } from '../api/client';

const chunkError = new TypeError('Failed to fetch dynamically imported module: /assets/ProductDetail.js');

function ThrowChunkError(): React.JSX.Element {
  throw chunkError;
}

describe('ChunkLoadRecovery', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  afterEach(() => {
    clearStoredAccessToken();
    vi.restoreAllMocks();
  });

  it('distinguishes chunk load errors from ordinary runtime errors', () => {
    expect(isChunkLoadError(chunkError)).toBe(true);
    expect(isChunkLoadError(new Error('ordinary render failure'))).toBe(false);
  });

  it('automatically reloads at most once for an app version', () => {
    const reloadWindow = vi.fn();

    expect(maybeReloadAfterChunkLoadError({
      appVersion: 'v1',
      error: chunkError,
      reloadWindow,
    })).toBe(true);
    expect(maybeReloadAfterChunkLoadError({
      appVersion: 'v1',
      error: chunkError,
      reloadWindow,
    })).toBe(false);
    expect(reloadWindow).toHaveBeenCalledTimes(1);
  });

  it('does not clear the auth session after a chunk failure', () => {
    const reloadWindow = vi.fn();
    storeAccessToken('jwt-for-test');

    maybeReloadAfterChunkLoadError({
      appVersion: 'v2',
      error: chunkError,
      reloadWindow,
    });

    expect(getStoredAccessToken()).toBe('jwt-for-test');
  });

  it('shows a manual recovery message after the automatic reload was already tried', () => {
    const reloadWindow = vi.fn();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    window.sessionStorage.setItem('telegram_shop_chunk_reload:v3', '1');

    render(
      <ChunkLoadRecovery appVersion="v3" resetKey="/product/1" reloadWindow={reloadWindow}>
        <ThrowChunkError />
      </ChunkLoadRecovery>,
    );

    expect(reloadWindow).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toContain('Не удалось загрузить обновление');

    fireEvent.click(screen.getByRole('button', { name: 'Повторить загрузку' }));
    expect(reloadWindow).toHaveBeenCalledTimes(1);
  });
});
