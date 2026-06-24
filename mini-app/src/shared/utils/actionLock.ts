export type ActionLock = {
  current: boolean;
};

export async function runLockedAction<T>(
  lock: ActionLock,
  action: () => Promise<T>,
): Promise<T | undefined> {
  if (lock.current) {
    return undefined;
  }

  lock.current = true;
  try {
    return await action();
  } finally {
    lock.current = false;
  }
}
