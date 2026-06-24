import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiClientError } from '../api/client';
import { NetworkBanner } from './NetworkBanner';
import {
  getNetworkState,
  handleNavigatorOffline,
  handleNavigatorOnline,
  markNetworkRequestFailure,
  markNetworkRequestSuccess,
  setNetworkState,
} from './networkState';

describe('network state and banner', () => {
  afterEach(() => {
    setNetworkState('online');
  });

  it('moves through offline, recovering, slow, and online states', () => {
    setNetworkState('online');

    handleNavigatorOffline();
    expect(getNetworkState()).toBe('offline');

    handleNavigatorOnline();
    expect(getNetworkState()).toBe('recovering');

    markNetworkRequestSuccess(3_000);
    expect(getNetworkState()).toBe('slow');

    markNetworkRequestFailure(new ApiClientError({ kind: 'timeout', message: 'timeout' }));
    expect(getNetworkState()).toBe('recovering');

    markNetworkRequestSuccess(100);
    expect(getNetworkState()).toBe('online');
  });

  it('shows a non-blocking banner and exposes manual retry outside online state', () => {
    const onRetry = vi.fn();
    const { rerender } = render(<NetworkBanner state="online" onRetry={onRetry} />);

    expect(screen.queryByRole('status')).toBeNull();

    rerender(<NetworkBanner state="offline" onRetry={onRetry} />);
    expect(screen.getByRole('status')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    rerender(<NetworkBanner state="recovering" onRetry={onRetry} />);
    expect(screen.getByRole('status')?.textContent).toContain('Проверяем');

    rerender(<NetworkBanner state="slow" onRetry={onRetry} />);
    expect(screen.getByRole('status')?.textContent).toContain('медленная');
  });
});
