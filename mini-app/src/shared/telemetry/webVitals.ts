let started = false;

type VitalEventName =
  | 'web_vital.lcp'
  | 'web_vital.inp'
  | 'web_vital.cls'
  | 'web_vital.ttfb'
  | 'web_vital.fcp';
type VitalReporter = (name: VitalEventName, value: number) => void;

let reportVital: VitalReporter | undefined;

export function startWebVitalsTelemetry(reporter: VitalReporter) {
  if (started || typeof PerformanceObserver === 'undefined') {
    return;
  }
  reportVital = reporter;
  started = true;
  observePaint();
  observeLcp();
  observeCls();
  observeInp();
  observeTtfb();
}

function observePaint() {
  observe('paint', (entries) => {
    for (const entry of entries) {
      if (entry.name === 'first-contentful-paint') {
        sendVital('web_vital.fcp', entry.startTime);
      }
    }
  });
}

function observeLcp() {
  observe('largest-contentful-paint', (entries) => {
    const latest = entries[entries.length - 1];
    if (latest) {
      sendVital('web_vital.lcp', latest.startTime);
    }
  });
}

function observeCls() {
  let cls = 0;
  observe('layout-shift', (entries) => {
    for (const entry of entries as LayoutShiftEntry[]) {
      if (!entry.hadRecentInput) {
        cls += entry.value;
      }
    }
  });
  window.addEventListener('pagehide', () => sendVital('web_vital.cls', cls), { once: true });
}

function observeInp() {
  let worstInteraction = 0;
  observe('event', (entries) => {
    for (const entry of entries as PerformanceEventTiming[]) {
      if (entry.duration > worstInteraction) {
        worstInteraction = entry.duration;
      }
    }
  }, { durationThreshold: 40 } as PerformanceObserverInit);
  window.addEventListener('pagehide', () => {
    if (worstInteraction > 0) {
      sendVital('web_vital.inp', worstInteraction);
    }
  }, { once: true });
}

function observeTtfb() {
  const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
  if (navigation) {
    sendVital('web_vital.ttfb', Math.max(0, navigation.responseStart - navigation.requestStart));
  }
}

function sendVital(name: VitalEventName, value: number) {
  if (!Number.isFinite(value) || value < 0) {
    return;
  }
  reportVital?.(name, value);
}

function observe(
  type: string,
  callback: (entries: PerformanceEntry[]) => void,
  options: PerformanceObserverInit = {},
) {
  try {
    const observer = new PerformanceObserver((list) => callback(list.getEntries()));
    observer.observe({ type, buffered: true, ...options });
  } catch {
    // Some Telegram WebView versions do not support every entry type.
  }
}

type LayoutShiftEntry = PerformanceEntry & {
  value: number;
  hadRecentInput: boolean;
};
