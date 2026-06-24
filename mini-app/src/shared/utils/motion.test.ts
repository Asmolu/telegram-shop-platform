import { afterEach, describe, expect, it, vi } from 'vitest';
import { getMotionAwareScrollBehavior, prefersReducedMotion } from './motion';

describe('motion preferences', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reduces scripted smooth scrolling when the user prefers reduced motion', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      media: '(prefers-reduced-motion: reduce)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));

    expect(prefersReducedMotion()).toBe(true);
    expect(getMotionAwareScrollBehavior()).toBe('auto');
  });

  it('keeps smooth scrolling when reduced motion is not requested', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false,
      media: '(prefers-reduced-motion: reduce)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));

    expect(prefersReducedMotion()).toBe(false);
    expect(getMotionAwareScrollBehavior()).toBe('smooth');
  });
});
