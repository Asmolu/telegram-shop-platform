import React from 'react';
import {
  getNetworkState,
  handleNavigatorOffline,
  handleNavigatorOnline,
  setNetworkState,
  subscribeNetworkState,
  type NetworkState,
} from './networkState';

type NetworkContextValue = {
  state: NetworkState;
  retry: () => void;
};

const NetworkContext = React.createContext<NetworkContextValue | null>(null);

export function NetworkProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<NetworkState>(getNetworkState);

  React.useEffect(() => subscribeNetworkState(setState), []);

  React.useEffect(() => {
    window.addEventListener('online', handleNavigatorOnline);
    window.addEventListener('offline', handleNavigatorOffline);
    if (navigator.onLine === false) {
      handleNavigatorOffline();
    }
    return () => {
      window.removeEventListener('online', handleNavigatorOnline);
      window.removeEventListener('offline', handleNavigatorOffline);
    };
  }, []);

  const retry = React.useCallback(() => {
    setNetworkState('recovering');
    window.dispatchEvent(new Event('miniapp:network-retry'));
  }, []);

  const value = React.useMemo(() => ({ state, retry }), [retry, state]);

  return <NetworkContext.Provider value={value}>{children}</NetworkContext.Provider>;
}

export function useNetworkState() {
  const context = React.useContext(NetworkContext);
  if (!context) {
    throw new Error('useNetworkState must be used within NetworkProvider');
  }
  return context;
}

export function useNetworkRetry(handler: () => void) {
  const stableHandler = React.useRef(handler);
  React.useEffect(() => {
    stableHandler.current = handler;
  }, [handler]);

  React.useEffect(() => {
    const listener = () => stableHandler.current();
    window.addEventListener('miniapp:network-retry', listener);
    window.addEventListener('miniapp:network-restored', listener);
    return () => {
      window.removeEventListener('miniapp:network-retry', listener);
      window.removeEventListener('miniapp:network-restored', listener);
    };
  }, []);
}
