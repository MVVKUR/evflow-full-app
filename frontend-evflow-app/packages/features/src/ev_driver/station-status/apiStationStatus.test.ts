import { describe, expect, it, vi } from 'vitest';

vi.mock('react-native', () => ({ NativeModules: {} }));

import { getApiStationLiveStatus } from './apiStationStatus';

const stationId = 'station-1';

function statusResponse(overrides: Record<string, unknown> = {}) {
  return {
    station_id: stationId,
    station_status: 1,
    available: '3',
    total: '5',
    waiting_time: 7.5,
    connectors: [
      {
        type: 'CCS2',
        speed_tier: 'fast',
        available: '2',
        total: '3',
        waiting_time: '12.4'
      },
      {
        type: '',
        speed_tier: null,
        available: '1',
        total: '2',
        waiting_time: '0'
      }
    ],
    ...overrides
  };
}

function occupancyResponse(overrides: Record<string, unknown> = {}) {
  return {
    station_id: stationId,
    days: [
      {
        day_of_week: 1,
        day_name: 'Monday',
        hours: [
          { hour_of_day: 3, avg_occupancy: -10 },
          { hour_of_day: 8, avg_occupancy: 45.5 },
          { hour_of_day: 23, avg_occupancy: 140 },
          { hour_of_day: 24, avg_occupancy: 60 }
        ]
      },
      {
        day_of_week: 7,
        day_name: 'Sunday',
        hours: [{ hour_of_day: 12, avg_occupancy: 25 }]
      }
    ],
    ...overrides
  };
}

function response(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as unknown as Response;
}

function makeFetcher(statusBody: unknown, occupancyBody: unknown) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    return url.endsWith('/status') ? response(statusBody) : response(occupancyBody);
  }) as unknown as typeof fetch;
}

describe('getApiStationLiveStatus', () => {
  it('expands grouped connectors and maps occupied waiting times defensively', async () => {
    const result = await getApiStationLiveStatus(stationId, makeFetcher(statusResponse(), occupancyResponse()));

    expect(result.connectors).toHaveLength(5);
    expect(result.connectors.map((connector) => connector.status)).toEqual([
      'available', 'available', 'occupied', 'available', 'occupied'
    ]);
    expect(result.connectors[2]).toMatchObject({
      connectorId: 'station-1:CCS2:fast:2',
      connectorType: 'CCS2',
      powerKw: null,
      estimatedWaitMinutes: 12.4,
      estimatedAvailableAt: null
    });
    expect(result.connectors[4]).toMatchObject({
      connectorId: 'station-1:Unknown connector:unknown:4',
      connectorType: 'Unknown connector',
      status: 'occupied',
      estimatedWaitMinutes: 7.5
    });
  });

  it('clamps available counts to parsed physical totals', async () => {
    const status = statusResponse({
      available: '9',
      total: '3',
      connectors: [{
        type: 'CCS2', speed_tier: 'fast', available: '9', total: '3', waiting_time: '-4'
      }]
    });
    const result = await getApiStationLiveStatus(stationId, makeFetcher(status, occupancyResponse()));
    expect(result.connectors).toHaveLength(3);
    expect(result.connectors.every((connector) => connector.status === 'available')).toBe(true);
    expect(result.peakHours.currentOccupancyPercent).toBe(0);
  });

  it('builds Monday-through-Sunday data, fills gaps, clamps occupancy, and maps Sunday to zero', async () => {
    const result = await getApiStationLiveStatus(stationId, makeFetcher(statusResponse(), occupancyResponse()));
    const [monday, tuesday, , , , , sunday] = result.peakHours.days;

    expect(result.peakHours.days.map((day) => day.dayOfWeek)).toEqual([1, 2, 3, 4, 5, 6, 0]);
    expect(monday.hourlyOccupancyPercent).toHaveLength(24);
    expect(monday.hourlyOccupancyPercent[3]).toBe(0);
    expect(monday.hourlyOccupancyPercent[8]).toBe(45.5);
    expect(monday.hourlyOccupancyPercent[23]).toBe(100);
    expect(tuesday.hourlyOccupancyPercent).toEqual(Array(24).fill(0));
    expect(sunday.hourlyOccupancyPercent[12]).toBe(25);
    expect(result.peakHours.currentOccupancyPercent).toBe(40);
  });

  it('rejects responses for a different station', async () => {
    await expect(getApiStationLiveStatus(
      stationId,
      makeFetcher(statusResponse({ station_id: 'other' }), occupancyResponse())
    )).rejects.toThrow('The station status response does not match the selected station.');

    await expect(getApiStationLiveStatus(
      stationId,
      makeFetcher(statusResponse(), occupancyResponse({ station_id: 'other' }))
    )).rejects.toThrow('The station occupancy response does not match the selected station.');
  });

  it('rejects an invalid API response', async () => {
    await expect(getApiStationLiveStatus(
      stationId,
      makeFetcher(statusResponse({ connectors: null }), occupancyResponse())
    )).rejects.toThrow('The station returned an invalid live status response.');
  });

  it('surfaces API failures without returning mock data', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      return url.endsWith('/status')
        ? response({}, false, 503)
        : response(occupancyResponse());
    }) as unknown as typeof fetch;

    await expect(getApiStationLiveStatus(stationId, fetcher))
      .rejects.toThrow('Unable to load live station status. Request failed with status 503');
  });
});
