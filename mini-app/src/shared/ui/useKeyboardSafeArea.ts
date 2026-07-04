import React from 'react';
import { getTelegramWebApp } from '../telegram/webApp';
import { getMotionAwareScrollBehavior } from '../utils/motion';

const TEXT_ENTRY_SELECTOR = [
  'textarea',
  'select',
  '[contenteditable="true"]',
  [
    'input:not([type="button"])',
    ':not([type="checkbox"])',
    ':not([type="radio"])',
    ':not([type="range"])',
    ':not([type="file"])',
    ':not([type="color"])',
    ':not([type="submit"])',
    ':not([type="reset"])',
  ].join(''),
].join(', ');

const KEYBOARD_OPEN_THRESHOLD = 24;
const MAX_KEYBOARD_INSET = 420;

function isTextEntryElement(element: Element | null): element is HTMLElement {
  return Boolean(element?.matches(TEXT_ENTRY_SELECTOR));
}

function getKeyboardInset() {
  if (typeof window === 'undefined') {
    return 0;
  }

  const visualViewport = window.visualViewport;
  const visualViewportInset = visualViewport
    ? Math.max(0, window.innerHeight - visualViewport.height - visualViewport.offsetTop)
    : 0;
  const webApp = getTelegramWebApp();
  const telegramViewportInset = webApp?.viewportStableHeight && webApp.viewportHeight
    ? Math.max(0, webApp.viewportStableHeight - webApp.viewportHeight)
    : 0;

  return Math.round(Math.min(Math.max(visualViewportInset, telegramViewportInset), MAX_KEYBOARD_INSET));
}

function getScrollTarget(element: HTMLElement) {
  return element.closest<HTMLElement>('[data-keyboard-scroll-target]') ?? element;
}

export function ensureFocusedInputVisible(element: HTMLElement, keyboardInset = getKeyboardInset()) {
  if (typeof window === 'undefined') {
    return;
  }

  const target = getScrollTarget(element);
  const behavior = getMotionAwareScrollBehavior();
  const visualViewport = window.visualViewport;

  if (!visualViewport || visualViewport.height <= 0 || typeof window.scrollTo !== 'function') {
    target.scrollIntoView?.({
      behavior,
      block: 'center',
      inline: 'nearest',
    });
    return;
  }

  const rect = target.getBoundingClientRect();
  const viewportTop = visualViewport.offsetTop || 0;
  const viewportHeight = visualViewport.height;
  const bottomGuard = keyboardInset > KEYBOARD_OPEN_THRESHOLD ? 108 : 84;
  const visibleTop = viewportTop + 12;
  const visibleBottom = viewportTop + viewportHeight - bottomGuard;
  const visibleHeight = visibleBottom - visibleTop;

  if (visibleHeight <= rect.height + 16) {
    element.scrollIntoView?.({
      behavior,
      block: 'center',
      inline: 'nearest',
    });
    return;
  }

  if (rect.top >= visibleTop && rect.bottom <= visibleBottom) {
    return;
  }

  const targetTop = window.scrollY + rect.top;
  const desiredTop = targetTop - viewportTop - Math.max((visibleHeight - rect.height) / 2, 0);
  window.scrollTo({
    top: Math.max(0, desiredTop),
    behavior,
  });
}

export function useKeyboardInset() {
  const activeElementRef = React.useRef<HTMLElement | null>(null);
  const frameRef = React.useRef<number | null>(null);
  const timersRef = React.useRef<number[]>([]);
  const [keyboardInset, setKeyboardInset] = React.useState(0);

  React.useEffect(() => {
    const root = document.documentElement;
    const webApp = getTelegramWebApp();

    function clearVisibilityWork() {
      timersRef.current.forEach((timer) => window.clearTimeout(timer));
      timersRef.current = [];
      if (frameRef.current !== null) {
        if (typeof window.cancelAnimationFrame === 'function') {
          window.cancelAnimationFrame(frameRef.current);
        } else {
          window.clearTimeout(frameRef.current);
        }
        frameRef.current = null;
      }
    }

    function applyKeyboardState() {
      const nextInset = getKeyboardInset();
      const trackedInput = activeElementRef.current;
      const hasTrackedInput = Boolean(trackedInput && document.contains(trackedInput));
      const hasFocusedInput = isTextEntryElement(document.activeElement) || hasTrackedInput;
      const keyboardOpen = hasFocusedInput && nextInset > KEYBOARD_OPEN_THRESHOLD;

      root.style.setProperty('--keyboard-inset', `${keyboardOpen ? nextInset : 0}px`);
      root.classList.toggle('keyboard-input-focused', hasFocusedInput);
      root.classList.toggle('keyboard-open', keyboardOpen);
      root.dataset.keyboardOpen = keyboardOpen ? 'true' : 'false';
      setKeyboardInset(keyboardOpen ? nextInset : 0);
      return nextInset;
    }

    function queueVisibilityCheck(element = activeElementRef.current) {
      if (!element || frameRef.current !== null) {
        return;
      }

      const runVisibilityCheck = () => {
        frameRef.current = null;
        const activeElement = activeElementRef.current;
        if (!activeElement || !document.contains(activeElement)) {
          return;
        }
        ensureFocusedInputVisible(activeElement, getKeyboardInset());
      };

      frameRef.current = typeof window.requestAnimationFrame === 'function'
        ? window.requestAnimationFrame(runVisibilityCheck)
        : window.setTimeout(runVisibilityCheck, 16);
    }

    function scheduleVisibility(element = activeElementRef.current, delays = [0, 90, 240, 520]) {
      clearVisibilityWork();
      timersRef.current = delays.map((delay) =>
        window.setTimeout(() => queueVisibilityCheck(element), delay),
      );
    }

    function handleFocusIn(event: FocusEvent) {
      const target = event.target instanceof Element ? event.target : null;
      if (!isTextEntryElement(target)) {
        return;
      }

      activeElementRef.current = target;
      applyKeyboardState();
      scheduleVisibility(target);
    }

    function handleFocusOut(event: FocusEvent) {
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (target && target !== activeElementRef.current) {
        return;
      }

      window.setTimeout(() => {
        const activeElement = document.activeElement;
        if (isTextEntryElement(activeElement)) {
          activeElementRef.current = activeElement;
          applyKeyboardState();
          scheduleVisibility(activeElementRef.current, [0, 120]);
          return;
        }

        activeElementRef.current = null;
        clearVisibilityWork();
        applyKeyboardState();
      }, 0);
    }

    function handleInput() {
      if (!activeElementRef.current) {
        return;
      }

      applyKeyboardState();
      scheduleVisibility(activeElementRef.current, [0, 120, 320]);
    }

    function handleViewportChange() {
      applyKeyboardState();
      if (activeElementRef.current) {
        scheduleVisibility(activeElementRef.current, [0, 80, 220]);
      }
    }

    applyKeyboardState();
    document.addEventListener('focusin', handleFocusIn);
    document.addEventListener('focusout', handleFocusOut);
    document.addEventListener('input', handleInput, true);
    window.addEventListener('resize', handleViewportChange);
    window.visualViewport?.addEventListener('resize', handleViewportChange);
    window.visualViewport?.addEventListener('scroll', handleViewportChange);
    webApp?.onEvent?.('viewportChanged', handleViewportChange);

    return () => {
      clearVisibilityWork();
      document.removeEventListener('focusin', handleFocusIn);
      document.removeEventListener('focusout', handleFocusOut);
      document.removeEventListener('input', handleInput, true);
      window.removeEventListener('resize', handleViewportChange);
      window.visualViewport?.removeEventListener('resize', handleViewportChange);
      window.visualViewport?.removeEventListener('scroll', handleViewportChange);
      webApp?.offEvent?.('viewportChanged', handleViewportChange);
      root.style.setProperty('--keyboard-inset', '0px');
      root.classList.remove('keyboard-input-focused', 'keyboard-open');
      root.dataset.keyboardOpen = 'false';
    };
  }, []);

  return keyboardInset;
}

export function useEnsureFocusedInputVisible() {
  return useKeyboardInset();
}
