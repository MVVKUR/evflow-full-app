import { describe, expect, it, vi } from 'vitest';

vi.mock('react-native', () => ({ NativeModules: {} }));

import {
  EVFLOW_API_BASE_URL,
  fetchStationOccupancy,
  fetchStationStatus
} from './api';

function response(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body
  } as unknown as Response;
}

function makeFetcher(value: Response) {
  return vi.fn().mockResolvedValue(value) as unknown as typeof fetch;
}

describe('station live-data API', () => {
  it('requests the station status endpoint', async () => {
    const fetcher = makeFetcher(response({ station_id: 'station-1' }));
    await fetchStationStatus('station-1', fetcher);
    expect(fetcher).toHaveBeenCalledWith(`${EVFLOW_API_BASE_URL}/api/v1/stations/station-1/status`);
  });

  it('requests the station occupancy endpoint', async () => {
    const fetcher = makeFetcher(response({ station_id: 'station-1' }));
    await fetchStationOccupancy('station-1', fetcher);
    expect(fetcher).toHaveBeenCalledWith(`${EVFLOW_API_BASE_URL}/api/v1/stations/station-1/occupancy`);
  });

  it('encodes special characters in station IDs', async () => {
    const fetcher = makeFetcher(response({ station_id: 'station/a b?#' }));
    await fetchStationStatus('station/a b?#', fetcher);
    await fetchStationOccupancy('station/a b?#', fetcher);
    const encoded = encodeURIComponent('station/a b?#');
    expect(fetcher).toHaveBeenNthCalledWith(1, `${EVFLOW_API_BASE_URL}/api/v1/stations/${encoded}/status`);
    expect(fetcher).toHaveBeenNthCalledWith(2, `${EVFLOW_API_BASE_URL}/api/v1/stations/${encoded}/occupancy`);
  });

  it('includes the endpoint and HTTP status in errors', async () => {
    await expect(fetchStationStatus('station-1', makeFetcher(response({}, { ok: false, status: 503 }))))
      .rejects.toThrow('Unable to load live station status. Request failed with status 503');
    await expect(fetchStationOccupancy('station-1', makeFetcher(response({}, { ok: false, status: 502 }))))
      .rejects.toThrow('Unable to load station occupancy history. Request failed with status 502');
  });
});
