import { describe, expect, it, vi } from 'vitest';

vi.mock('react-native', () => ({ NativeModules: {} }));

import { getApiStationLiveStatus } from './apiStationStatus';

const stationId = 'station-1';

// Mirrors what the API actually returns: integer counts, in_use and
// out_of_service broken out, waiting_time a number or null, power_kw per group.
function statusResponse(overrides: Record<string, unknown> = {}) {
  return {
    station_id: stationId,
    station_status: 1,
    available: 3,
    total: 6,
    in_use: 2,
    out_of_service: 1,
    waiting_time: 7.5,
    connectors: [
      {
        type: 'CCS2',
        speed_tier: 'fast',
        power_kw: 60,
        available: 2,
        total: 4,
        in_use: 1,
        out_of_service: 1,
        waiting_time: 12.4
      },
      {
        type: '',
        speed_tier: null,
        power_kw: null,
        available: 1,
        total: 2,
        in_use: 1,
        out_of_service: 0,
        waiting_time: null
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
          { hour_of_day: 8, avg_occupancy: 45.5, occupancy_level: 'MODERATE' },
          { hour_of_day: 23, avg_occupancy: 140, occupancy_level: 'PEAK' },
          { hour_of_day: 24, avg_occupancy: 60, occupancy_level: 'BUSY' }
        ]
      },
      {
        day_of_week: 7,
        day_name: 'Sunday',
        hours: [{ hour_of_day: 12, avg_occupancy: 25, occupancy_level: 'MODERATE' }]
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
  it('expands each group into available, occupied and out-of-service plugs', async () => {
    const result = await getApiStationLiveStatus(stationId, makeFetcher(statusResponse(), occupancyResponse()));

    expect(result.connectors).toHaveLength(6);
    expect(result.connectors.map((connector) => connector.status)).toEqual([
      'available', 'available', 'occupied', 'out_of_service', 'available', 'occupied'
    ]);
    expect(result.connectors[2]).toMatchObject({
      connectorId: 'station-1:CCS2:fast:2',
      connectorType: 'CCS2',
      powerKw: 60,
      status: 'occupied',
      estimatedWaitMinutes: 12.4
    });
  });

  it('never attaches a wait estimate to a broken plug', async () => {
    // The whole point of the out_of_service count: total - available would have
    // folded this plug into "occupied" and promised the driver it frees up.
    const result = await getApiStationLiveStatus(stationId, makeFetcher(statusResponse(), occupancyResponse()));
    const broken = result.connectors.filter((connector) => connector.status === 'out_of_service');

    expect(broken).toHaveLength(1);
    expect(broken[0].estimatedWaitMinutes).toBeNull();
    expect(broken[0].powerKw).toBe(60);
  });

  it('keeps an unknown wait as null rather than reporting zero minutes', async () => {
    const status = statusResponse({
      available: 0,
      total: 2,
      in_use: 2,
      out_of_service: 0,
      waiting_time: null,
      connectors: [{
        type: 'CCS2', speed_tier: 'fast', power_kw: 60,
        available: 0, total: 2, in_use: 2, out_of_service: 0, waiting_time: null
      }]
    });
    const result = await getApiStationLiveStatus(stationId, makeFetcher(status, occupancyResponse()));

    expect(result.connectors).toHaveLength(2);
    expect(result.connectors.every((connector) => connector.estimatedWaitMinutes === null)).toBe(true);
  });

  it('falls back to the station-wide wait only when the group has none', async () => {
    const result = await getApiStationLiveStatus(stationId, makeFetcher(statusResponse(), occupancyResponse()));
    const lastOccupied = result.connectors[5];

    expect(lastOccupied).toMatchObject({ status: 'occupied', estimatedWaitMinutes: 7.5, powerKw: null });
  });

  it('reports occupancy over every plug, counting only the busy ones', async () => {
    // in_use / total, so a broken plug is neither busy nor free. Same
    // denominator the backend uses for historical avg_occupancy.
    const result = await getApiStationLiveStatus(stationId, makeFetcher(statusResponse(), occupancyResponse()));

    expect(result.peakHours.currentOccupancyPercent).toBe(33);
  });

  it('maps ISO weekdays onto JS day indexes, clamps, and ignores out-of-range hours', async () => {
    const result = await getApiStationLiveStatus(stationId, makeFetcher(statusResponse(), occupancyResponse()));
    const [monday, tuesday, , , , , sunday] = result.peakHours.days;

    expect(result.peakHours.days.map((day) => day.dayOfWeek)).toEqual([1, 2, 3, 4, 5, 6, 0]);
    expect(monday.hourlyOccupancyPercent).toHaveLength(24);
    expect(monday.hourlyOccupancyPercent[8]).toBe(45.5);
    expect(monday.hourlyOccupancyPercent[23]).toBe(100);
    expect(tuesday.hourlyOccupancyPercent).toEqual(Array(24).fill(0));
    expect(sunday.hourlyOccupancyPercent[12]).toBe(25);
    expect(result.peakHours.hasHistory).toBe(true);
  });

  it('flags a station with no history instead of passing zeros off as measurements', async () => {
    const result = await getApiStationLiveStatus(
      stationId,
      makeFetcher(statusResponse(), occupancyResponse({ days: [] }))
    );

    expect(result.peakHours.hasHistory).toBe(false);
    // The zero-filled week is layout scaffolding; hasHistory is what callers read.
    expect(result.peakHours.days).toHaveLength(7);
    expect(result.peakHours.days.every((day) => day.hourlyOccupancyPercent.every((percent) => percent === 0))).toBe(true);
  });

  it('rejects the pre-integer response shape instead of coercing it', async () => {
    // Guards against a server rollback silently resurrecting the string counts
    // the client used to parse, which is how "0" became a promised wait.
    await expect(getApiStationLiveStatus(
      stationId,
      makeFetcher(statusResponse({ available: '3', total: '6' }), occupancyResponse())
    )).rejects.toThrow('The station returned an invalid live status response.');
  });

  it('rejects an occupancy hour with no classification', async () => {
    await expect(getApiStationLiveStatus(
      stationId,
      makeFetcher(statusResponse(), occupancyResponse({
        days: [{ day_of_week: 1, day_name: 'Monday', hours: [{ hour_of_day: 8, avg_occupancy: 45.5 }] }]
      }))
    )).rejects.toThrow('The station returned an invalid live status response.');
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
