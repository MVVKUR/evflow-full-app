import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-native', () => ({ NativeModules: {} }));
vi.mock('../auth/session', () => ({ getAuthHeaders: vi.fn() }));

import { getAuthHeaders } from '../auth/session';
import { EVFLOW_API_BASE_URL } from '../stations/api';
import {
  fetchPlannerBenchmark,
  fetchPlannerCandidates,
  fetchPlannerCell,
  fetchPlannerCells,
  fetchPlannerRoi,
  PlannerApiError
} from './api';

const mockedGetAuthHeaders = vi.mocked(getAuthHeaders);
const auth = { Authorization: 'Bearer planner-token' };

function response(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  const value = {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body
  };
  return { ...value, clone: () => ({ ...value }) } as unknown as Response;
}

function fetcherReturning(value: Response) {
  return vi.fn().mockResolvedValue(value) as unknown as typeof fetch;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedGetAuthHeaders.mockReturnValue(auth);
});

describe('planner API client', () => {
  it('loads candidates with the backend default weights and planner auth', async () => {
    const payload = { candidates: [] };
    const fetcher = fetcherReturning(response(payload));
    await expect(fetchPlannerCandidates({}, fetcher)).resolves.toBe(payload);

    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/planner/candidates?clusters=15&quantile=0.9`);
    expect(options.headers).toMatchObject({ ...auth, 'Content-Type': 'application/json' });
    expect(JSON.parse(options.body)).toEqual({ coverage: 0.35, population: 0.35, activity: 0.2, roads: 0.1 });
  });

  it('serializes the Leaflet viewport in backend bbox order', async () => {
    const fetcher = fetcherReturning(response({ features: [] }));
    await fetchPlannerCells({ west: 106.6, south: -6.4, east: 107, north: -6, metric: 'score' }, fetcher);
    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    const parsed = new URL(url);
    expect(parsed.pathname).toBe('/api/v1/planner/cells.geojson');
    expect(parsed.searchParams.get('bbox')).toBe('106.6,-6.4,107,-6');
    expect(parsed.searchParams.get('limit')).toBe('10000');
    expect(options.headers).toMatchObject(auth);
  });

  it('encodes cell IDs for detail and benchmark requests', async () => {
    const fetcher = fetcherReturning(response({}));
    await fetchPlannerCell('cell / one', fetcher);
    await fetchPlannerBenchmark('cell / one', 5, fetcher);
    const calls = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[0][0]).toContain('/cells/cell%20%2F%20one');
    expect(calls[1][0]).toContain('/benchmark/cell%20%2F%20one?radius_km=5&limit=10');
  });

  it('fails before fetch when no planner session exists', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = fetcherReturning(response({}));
    await expect(fetchPlannerCandidates({}, fetcher)).rejects.toMatchObject({ status: 401 });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('preserves backend role errors', async () => {
    const fetcher = fetcherReturning(response({ detail: 'this endpoint requires a planner account' }, { ok: false, status: 403 }));
    await expect(fetchPlannerCandidates({}, fetcher)).rejects.toEqual(
      new PlannerApiError(403, 'this endpoint requires a planner account')
    );
  });

  it('posts a typed ROI request with planner auth and JSON content', async () => {
    const payload = {
      cell_id: 'JBDTBK_22219', payback_years: null, breaks_even: false,
      input_sources: { capex_per_connector_idr: 'planner' }
    };
    const fetcher = fetcherReturning(response(payload));
    const input = {
      cell_id: 'JBDTBK_22219', capex_per_connector_idr: 250_000_000,
      opex_monthly_idr: 15_000_000, utilisation_target: 0.2
    };

    await expect(fetchPlannerRoi(input, fetcher)).resolves.toBe(payload);
    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/planner/roi`);
    expect(options.method).toBe('POST');
    expect(options.headers).toMatchObject({ ...auth, 'Content-Type': 'application/json' });
    expect(JSON.parse(options.body)).toEqual(input);
  });

  it.each([
    [401, 'missing bearer token'],
    [403, 'this endpoint requires a planner account'],
    [422, 'assumed demand exceeds hardware capacity']
  ])('preserves ROI error %s detail', async (status, detail) => {
    const fetcher = fetcherReturning(response({ detail }, { ok: false, status }));
    await expect(fetchPlannerRoi({
      cell_id: 'cell', capex_per_connector_idr: 1,
      opex_monthly_idr: 1, utilisation_target: 0.2
    }, fetcher)).rejects.toEqual(new PlannerApiError(status, detail));
  });

  it('surfaces Pydantic validation detail for an invalid ROI demand basis', async () => {
    const fetcher = fetcherReturning(response({
      detail: [{ type: 'value_error', loc: ['body'], msg: 'supply exactly one demand input' }]
    }, { ok: false, status: 422 }));

    await expect(fetchPlannerRoi({
      cell_id: 'cell', capex_per_connector_idr: 1,
      opex_monthly_idr: 1, utilisation_target: 0.2
    }, fetcher)).rejects.toEqual(new PlannerApiError(422, 'supply exactly one demand input'));
  });
});
