import { describe, expect, it } from 'vitest';
import { availableStationStatusFixture, getMockStationLiveStatus, occupiedStationStatusFixture } from './mockStationStatus';
import { isValidStationLiveStatus } from './types';

describe('mock station status fixtures', () => {
  it.each([availableStationStatusFixture, occupiedStationStatusFixture])('contains seven complete 24-hour days', (fixture) => {
    expect(isValidStationLiveStatus(fixture)).toBe(true);
    expect(fixture.peakHours.days).toHaveLength(7);
    fixture.peakHours.days.forEach((day) => expect(day.hourlyOccupancyPercent).toHaveLength(24));
  });

  it('selects fixtures deterministically from station ID', async () => {
    expect(await getMockStationLiveStatus('station-42')).toEqual(await getMockStationLiveStatus('station-42'));
  });
});
