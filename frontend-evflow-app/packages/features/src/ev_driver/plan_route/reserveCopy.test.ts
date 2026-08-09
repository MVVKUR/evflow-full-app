import { describe, expect, it } from 'vitest';
import { getReserveCopy } from './reserveCopy';

describe('getReserveCopy', () => {
  it('never claims "below" when the projection is above the reserve', () => {
    // The exact screenshot regression: 23% projected against a 20% reserve.
    expect(getReserveCopy(23, 20)).not.toMatch(/below/i);
  });

  it('says below only when it really is below', () => {
    expect(getReserveCopy(12, 20)).toBe('Projected arrival is below your 20% reserve.');
    expect(getReserveCopy(19.9, 20)).toMatch(/below/i);
  });

  it('calls out a tight margin instead of staying silent', () => {
    expect(getReserveCopy(23, 20)).toBe('Projected arrival clears your 20% reserve by only 3%.');
    expect(getReserveCopy(20, 20)).toMatch(/only 0%/);
  });

  it('adds no line when the margin is comfortable', () => {
    expect(getReserveCopy(60, 20)).toBeNull();
  });

  it('makes no claim without a projection', () => {
    expect(getReserveCopy(null, 20)).toBeNull();
    expect(getReserveCopy(undefined, 20)).toBeNull();
    expect(getReserveCopy(Number.NaN, 20)).toBeNull();
  });
});
