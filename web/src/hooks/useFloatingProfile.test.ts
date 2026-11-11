import { expect, it } from 'vitest';
import { measureFloatingBounds, normalizeProgressRatio, ratioToTop, topToRatio } from './useFloatingProfile';
it('uses real host, navigation, composer and card rectangles with eight pixel clearance', () => {
  const bounds = measureFloatingBounds({ top: 50, bottom: 500 } as DOMRect, { bottom: 90 } as DOMRect, { top: 430 } as DOMRect, 100);
  expect(bounds).toEqual({ minimumTop: 48, maximumTop: 272, availableHeight: 324, travel: 224 });
  expect(ratioToTop(.5, bounds)).toBe(160);
  expect(topToRatio(999, bounds, .5)).toBe(1);
});
it('retains ratio without travel and normalizes invalid values', () => {
  expect(normalizeProgressRatio(NaN)).toBe(.5);
  expect(normalizeProgressRatio(2)).toBe(1);
  expect(topToRatio(10, { minimumTop: 10, maximumTop: 10, availableHeight: 20, travel: 0 }, .7)).toBe(.7);
});
