import { describe, expect, it } from 'vitest';
import { getStationAvailabilityBand, stationBandColors } from './stationAvailabilityBand';

const band = getStationAvailabilityBand;

describe('getStationAvailabilityBand', () => {
  it('calls a station with nothing free full', () => {
    expect(band(0, 4)).toBe('full');
  });

  it('calls a station with a third or less free limited', () => {
    expect(band(1, 3)).toBe('limited');
    expect(band(2, 6)).toBe('limited');
    expect(band(1, 10)).toBe('limited');
  });

  it('calls anything more than a third free', () => {
    expect(band(2, 5)).toBe('free');
    expect(band(4, 4)).toBe('free');
  });

  // A station we know nothing about must not be painted red. Claiming "full"
  // would state a fact we do not have, and red is the colour a driver acts on.
  it('does not claim full when the counts are missing', () => {
    expect(band(null, null)).toBe('unknown');
    expect(band(undefined, 4)).toBe('unknown');
    expect(band(2, null)).toBe('unknown');
  });

  it('treats a station with no connectors on record as unknown, not full', () => {
    expect(band(0, 0)).toBe('unknown');
  });

  it('gives every band a distinct colour', () => {
    const values = Object.values(stationBandColors);
    expect(new Set(values).size).toBe(values.length);
  });
});
