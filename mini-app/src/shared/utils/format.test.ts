import { describe, expect, it } from 'vitest';
import { getDiscountBadgeTier } from './format';

describe('getDiscountBadgeTier', () => {
  it.each([
    [1, 1],
    [20, 1],
    [21, 2],
    [40, 2],
    [41, 3],
    [60, 3],
    [61, 4],
    [80, 4],
    [81, 5],
    [99, 5],
    [100, 5],
  ] as const)('maps %i percent to tier %i', (percent, tier) => {
    expect(getDiscountBadgeTier(percent)).toBe(tier);
  });

  it.each([0, -1, Number.NaN, null, undefined])('ignores invalid percent %s', (percent) => {
    expect(getDiscountBadgeTier(percent)).toBeNull();
  });
});
