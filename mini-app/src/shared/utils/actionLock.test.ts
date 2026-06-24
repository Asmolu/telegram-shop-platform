import { describe, expect, it, vi } from 'vitest';
import { runLockedAction } from './actionLock';

describe('runLockedAction', () => {
  it('does not run a second mutation while the first one is still active', async () => {
    const lock = { current: false };
    let releaseFirst: (value: string) => void = () => undefined;
    const action = vi.fn(() => (
      new Promise<string>((resolve) => {
        releaseFirst = resolve;
      })
    ));

    const first = runLockedAction(lock, action);
    const second = runLockedAction(lock, action);

    expect(action).toHaveBeenCalledTimes(1);
    await expect(second).resolves.toBeUndefined();

    releaseFirst('done');
    await expect(first).resolves.toBe('done');
    expect(lock.current).toBe(false);
  });
});
