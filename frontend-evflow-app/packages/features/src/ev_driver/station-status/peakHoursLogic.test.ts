import { describe, expect, it } from 'vitest';
import {
  availabilityBandLabels,
  createPeakHourBars,
  getAvailabilityBand,
  getJakartaDayAndHour,
  getLowDemandRecommendation,
  selectPeakHoursDay
} from './peakHoursLogic';
import type { AvailabilityBand } from './peakHoursLogic';
import type { DailyPeakHours } from './types';

const monday: DailyPeakHours = { dayOfWeek: 1, hourlyOccupancyPercent: Array.from({ length: 24 }, (_, hour) => hour * 4) };
const tuesday: DailyPeakHours = { dayOfWeek: 2, hourlyOccupancyPercent: Array.from({ length: 24 }, (_, hour) => 100 - hour * 4) };

describe('peak hours logic', () => {
  it('compares server buckets with the current Jakarta weekday and hour', () => {
    expect(getJakartaDayAndHour(new Date('2026-08-21T18:30:00Z'))).toEqual({
      dayOfWeek: 6,
      hour: 1
    });
  });

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

describe('availability bands', () => {
  // The product specified the bands on AVAILABILITY, so each case is written the
  // way it was specified and the occupancy the chart actually holds is derived
  // here. Every stated edge of every band is present: 100, 70, 69, 30, 29, 0.
  const boundaries: Array<{ availabilityPercent: number; band: AvailabilityBand }> = [
    { availabilityPercent: 100, band: 'green' },
    { availabilityPercent: 71, band: 'green' },
    { availabilityPercent: 70, band: 'green' },
    { availabilityPercent: 69, band: 'yellow' },
    { availabilityPercent: 68, band: 'yellow' },
    { availabilityPercent: 31, band: 'yellow' },
    { availabilityPercent: 30, band: 'yellow' },
    { availabilityPercent: 29, band: 'red' },
    { availabilityPercent: 28, band: 'red' },
    { availabilityPercent: 1, band: 'red' },
    { availabilityPercent: 0, band: 'red' }
  ];

  boundaries.forEach(({ availabilityPercent, band }) => {
    it(`puts ${availabilityPercent} percent availability in the ${band} band`, () => {
      expect(getAvailabilityBand(100 - availabilityPercent)).toBe(band);
    });
  });

  it('reads the bands off occupancy, which is the inverse of the specified availability', () => {
    expect(getAvailabilityBand(0)).toBe('green');
    expect(getAvailabilityBand(30)).toBe('green');
    expect(getAvailabilityBand(31)).toBe('yellow');
    expect(getAvailabilityBand(70)).toBe('yellow');
    expect(getAvailabilityBand(71)).toBe('red');
    expect(getAvailabilityBand(100)).toBe('red');
  });

  it('keeps the bands total across the fractional occupancy the API sends', () => {
    // The API stores occupancy rounded to two decimals, so values land between
    // the integer edges the product wrote down. Nothing may fall through.
    expect(getAvailabilityBand(29.99)).toBe('green'); // 70.01 available
    expect(getAvailabilityBand(30.01)).toBe('yellow'); // 69.99 available
    expect(getAvailabilityBand(69.99)).toBe('yellow'); // 30.01 available
    expect(getAvailabilityBand(70.01)).toBe('red'); // 29.99 available
  });

  it('clamps occupancy outside 0-100 instead of inventing a fourth band', () => {
    expect(getAvailabilityBand(-40)).toBe('green');
    expect(getAvailabilityBand(140)).toBe('red');
  });

  it('treats a non-finite occupancy as no measurement rather than as full', () => {
    expect(getAvailabilityBand(Number.NaN)).toBe('green');
    expect(getAvailabilityBand(Number.POSITIVE_INFINITY)).toBe('green');
  });

  it('bands every bar of a day, so no hour renders without a colour', () => {
    const bands = createPeakHourBars(tuesday).map((bar) => getAvailabilityBand(bar.occupancyPercent));
    expect(bands).toHaveLength(24);
    expect(bands.filter((band) => band === 'red')).toHaveLength(8); // occupancy 100 down to 72
    expect(bands.filter((band) => band === 'yellow')).toHaveLength(10); // occupancy 68 down to 32
    expect(bands.filter((band) => band === 'green')).toHaveLength(6); // occupancy 28 down to 4
  });

  it('names every band in words so colour is not the only signal', () => {
    const labels = Object.values(availabilityBandLabels);
    expect(labels).toHaveLength(3);
    expect(new Set(labels).size).toBe(3);
    labels.forEach((label) => expect(label.length).toBeGreaterThan(0));
    expect(availabilityBandLabels[getAvailabilityBand(0)]).toBe('mostly available');
  });
});
