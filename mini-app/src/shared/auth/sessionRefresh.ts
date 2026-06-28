type AuthSessionRefreshHandler = () => Promise<boolean>;

let refreshHandler: AuthSessionRefreshHandler | null = null;
let refreshInFlight: Promise<boolean> | null = null;

export function registerAuthSessionRefreshHandler(handler: AuthSessionRefreshHandler) {
  refreshHandler = handler;

  return () => {
    if (refreshHandler === handler) {
      refreshHandler = null;
    }
  };
}

export async function requestAuthSessionRefresh() {
  if (!refreshHandler) {
    return false;
  }

  if (!refreshInFlight) {
    refreshInFlight = refreshHandler()
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }

  return refreshInFlight;
}
