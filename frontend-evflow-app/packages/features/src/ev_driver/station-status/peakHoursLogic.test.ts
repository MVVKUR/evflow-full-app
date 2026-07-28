import { describe, expect, it } from 'vitest';
import { createPeakHourBars, getLowDemandRecommendation, selectPeakHoursDay } from './peakHoursLogic';
import type { DailyPeakHours } from './types';

const monday: DailyPeakHours = { dayOfWeek: 1, hourlyOccupancyPercent: Array.from({ length: 24 }, (_, hour) => hour * 4) };
const tuesday: DailyPeakHours = { dayOfWeek: 2, hourlyOccupancyPercent: Array.from({ length: 24 }, (_, hour) => 100 - hour * 4) };

describe('peak hours logic', () => {
  it('creates exactly 24 bars, one for every hour', () => {
    const bars = createPeakHourBars(monday);
    expect(bars).toHaveLength(24);
    expect(bars.map((bar) => bar.hour)).toEqual(Array.from({ length: 24 }, (_, hour) => hour));
  });

  it('changes the selected day data', () => {
    expect(selectPeakHoursDay([monday, tuesday], 1)).toBe(monday);
    expect(selectPeakHoursDay([monday, tuesday], 2)).toBe(tuesday);
  });

  it('derives a low-demand recommendation from the selected values', () => {
    expect(getLowDemandRecommendation(monday.hourlyOccupancyPercent)).toContain('Best times to visit: before');
    expect(getLowDemandRecommendation(tuesday.hourlyOccupancyPercent)).toContain('after');
  });
});
