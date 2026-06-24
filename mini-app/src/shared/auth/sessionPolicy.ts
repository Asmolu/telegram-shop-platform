import { isUnauthorizedError } from '../api';

export function shouldClearStoredTokenAfterAuthError(error: unknown) {
  return isUnauthorizedError(error);
}
