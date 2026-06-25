export type NetworkState = 'online' | 'slow' | 'offline' | 'recovering';
export type NetworkFailureEvent = {
  kind:
    | 'authentication'
    | 'validation'
    | 'network_unavailable'
    | 'timeout'
    | 'request_aborted'
    | 'rate_limited'
    | 'temporary_server_failure'
    | 'permanent_server_failure'
    | string;
};

type Listener = (state: NetworkState) => void;

const SLOW_REQUEST_THRESHOLD_MS = 2_800;
const listeners = new Set<Listener>();
let currentState: NetworkState = typeof navigator !== 'undefined' && navigator.onLine === false
  ? 'offline'
  : 'online';

export function getNetworkState() {
  return currentState;
}

export function subscribeNetworkState(listener: Listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function setNetworkState(state: NetworkState) {
  if (state === currentState) {
    return;
  }
  currentState = state;
  listeners.forEach((listener) => listener(currentState));
  void import('../telemetry').then(({ getConnectionTelemetry, trackTelemetry }) => {
    trackTelemetry('network.state_changed', {
      network_state: currentState,
      success: currentState === 'online',
      ...getConnectionTelemetry(),
    });
  });
}

export function markNetworkRequestStarted() {
  if (currentState === 'offline') {
    setNetworkState('recovering');
  }
}

export function markNetworkRequestSuccess(durationMs: number) {
  setNetworkState(durationMs >= SLOW_REQUEST_THRESHOLD_MS ? 'slow' : 'online');
}

export function markNetworkRequestFailure(error: NetworkFailureEvent) {
  if (error.kind === 'request_aborted' || error.kind === 'authentication' || error.kind === 'validation') {
    return;
  }
  if (error.kind === 'network_unavailable') {
    setNetworkState('offline');
    return;
  }
  if (
    error.kind === 'timeout'
    || error.kind === 'rate_limited'
    || error.kind === 'temporary_server_failure'
  ) {
    setNetworkState('recovering');
  }
}

export function handleNavigatorOnline() {
  setNetworkState('recovering');
}

export function handleNavigatorOffline() {
  setNetworkState('offline');
}
