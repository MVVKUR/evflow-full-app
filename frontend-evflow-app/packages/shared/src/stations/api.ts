import { toQueryString } from '../api/client';
import { getEvflowApiBaseUrl } from '../api/baseUrl';

export const EVFLOW_API_BASE_URL = getEvflowApiBaseUrl();

export type StationApiSource = 'pln_spklu' | 'open_charge_map' | 'osm';

export type StationApiItem = {
  id: string;
  name: string | null;
  sources: StationApiSource[];
  latitude: number;
  longitude: number;
  address: string | null;
  province: string | null;
  city: string | null;
  operator: string | null;
  power_kw: number | null;
  charge_type: string | null;
  speed_tier: string | null;
  connectors: StationConnectorApiItem[];
  /** Live plug counts. Absent on older servers, so treat as unknown rather than zero. */
  total_connectors?: number | null;
  available_connectors?: number | null;
  connector_types: StationConnectorTypeApiItem[];
  connector_inferred: boolean | null;
  status: string | null;
  date_verified: string | null;
  distance_km: number | null;
};

export type StationConnectorTypeApiItem =
  | string
  | {
      type?: string | null;
      count?: number | null;
      speed_tier?: string | null;
      power_kw?: number | null;
      type_inferred?: boolean | null;
    };

export type StationConnectorApiItem = {
  type: string;
  count: number;
  speed_tier: string | null;
  power_kw: number | null;
  type_inferred: boolean;
};

export type StationListApiResponse = {
  total: number;
  limit: number;
  offset: number;
  items: StationApiItem[];
};

/**
 * Live connector counts for one station.
 *
 * `total` is always `available + in_use + out_of_service`. Do not derive
 * occupancy as `total - available`: that folds broken connectors into the
 * occupied count and tells the driver to wait for a plug that will never free
 * up. Use `in_use` and `out_of_service` directly.
 *
 * `waiting_time` is minutes and has three states: `0` when a connector is free
 * right now, a positive number when none is free but an active session gives an
 * estimate, and `null` when none is free and no estimate can be computed. Null
 * must never be rendered as "~0 minutes".
 */
export type StationStatusApiResponse = {
  station_id: string;
  station_status: number;
  available: number;
  total: number;
  in_use: number;
  out_of_service: number;
  waiting_time: number | null;
  connectors: Array<{
    type: string;
    speed_tier: string | null;
    /** Rated power shared by the group. Two groups with the same type and speed tier are told apart by this. */
    power_kw: number | null;
    available: number;
    total: number;
    in_use: number;
    out_of_service: number;
    waiting_time: number | null;
  }>;
};

export type StationOccupancyLevel = 'LOW' | 'MODERATE' | 'BUSY' | 'PEAK';

/**
 * Historical occupancy, one entry per weekday-hour the backend has data for.
 *
 * `day_of_week` is ISO: 1 is Monday, 7 is Sunday. It does NOT line up with
 * `Date.prototype.getDay()`, where 0 is Sunday.
 *
 * `days` and `hours` may be sparse, and an empty `days` array means there is
 * not enough history yet — which is not the same as a week of zero occupancy.
 */
export type StationOccupancyApiResponse = {
  station_id: string;
  days: Array<{
    day_of_week: number;
    day_name: string;
    hours: Array<{
      hour_of_day: number;
      avg_occupancy: number;
      /** Classified server-side at 20/50/80 percent. Display this rather than re-deriving the buckets. */
      occupancy_level: StationOccupancyLevel;
    }>;
  }>;
};

export type StationListParams = {
  province?: string;
  city?: string;
  q?: string;
  minPower?: number;
  maxPower?: number;
  connectorType?: ConnectorTypeApiItem[];
  speedTier?: SpeedTierApiItem[];
  bbox?: string;
  limit?: number;
  offset?: number;
};

export type NearbyStationListParams = {
  lat: number;
  lon: number;
  radius: number;
  connectorType?: ConnectorTypeApiItem[];
  speedTier?: SpeedTierApiItem[];
  limit?: number;
};


export type ConnectorTypeApiItem = {
  name: string;
  count: number;
};

export type SpeedTierApiItem = {
  id: string;
  label: string;
  min_kw: number;
  max_kw: number | null;
  count: number;
};

export type StatsSourceCountApiItem = {
  source: string;
  count: number;
};

export type StatsNameCountApiItem = {
  name: string;
  count: number;
};

export type StatsApiResponse = {
  total: number;
  by_source: StatsSourceCountApiItem[];
  by_province: StatsNameCountApiItem[];
  by_charge_type: StatsNameCountApiItem[];
  with_power_kw: number;
  power_kw_min: number | null;
  power_kw_max: number | null;
  power_kw_mean: number | null;
};

export async function fetchStats(fetcher: typeof fetch = fetch) {
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/stats`);

  if (!response.ok) {
    throw new Error(`EVFlow stats request failed with status ${response.status}`);
  }

  return response.json() as Promise<StatsApiResponse>;
}

export async function fetchStations(params: StationListParams = {}, fetcher: typeof fetch = fetch) {
  const query = toQueryString({
    province: params.province,
    city: params.city,
    q: params.q,
    min_power: params.minPower,
    max_power: params.maxPower,
    connector_type: params.connectorType?.map((connector) => connector.name),
    speed_tier: params.speedTier?.map((speedTier) => speedTier.id),
    bbox: params.bbox,
    limit: params.limit,
    offset: params.offset
  });

  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/stations${query}`);

  if (!response.ok) {
    throw new Error(`EVFlow stations request failed with status ${response.status}`);
  }

  return response.json() as Promise<StationListApiResponse>;
}

export async function fetchNearbyStations(params: NearbyStationListParams, fetcher: typeof fetch = fetch) {
  const query = toQueryString({
    lat: params.lat,
    lon: params.lon,
    radius_km: params.radius,
    connector_type: params.connectorType?.map((connector) => connector.name),
    speed_tier: params.speedTier?.map((speedTier) => speedTier.id),
    limit: params.limit
  });

  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/stations/nearby${query}`);

  if (!response.ok) {
    throw new Error(`EVFlow nearby stations request failed with status ${response.status}`);
  }

  return response.json() as Promise<StationApiItem[]>;
}


export async function fetchConnectorTypes(fetcher: typeof fetch = fetch) {
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/connectors`);

  if (!response.ok) {
    throw new Error(`EVFlow connector types request failed with status ${response.status}`);
  }

  return response.json() as Promise<ConnectorTypeApiItem[]>;
}

export async function fetchSpeedTiers(fetcher: typeof fetch = fetch) {
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/speed-tiers`);

  if (!response.ok) {
    throw new Error(`EVFlow speed tiers request failed with status ${response.status}`);
  }

  return response.json() as Promise<SpeedTierApiItem[]>;
}

export async function fetchStation(id: string, fetcher: typeof fetch = fetch) {
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/stations/${id}`);

  if (!response.ok) {
    throw new Error(`EVFlow station request failed with status ${response.status}`);
  }

  return response.json() as Promise<StationApiItem>;
}

export async function fetchStationStatus(stationId: string, fetcher: typeof fetch = fetch) {
  const encodedStationId = encodeURIComponent(stationId);
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/stations/${encodedStationId}/status`);

  if (!response.ok) {
    throw new Error(`Unable to load live station status. Request failed with status ${response.status}`);
  }

  return response.json() as Promise<StationStatusApiResponse>;
}

export async function fetchStationOccupancy(stationId: string, fetcher: typeof fetch = fetch) {
  const encodedStationId = encodeURIComponent(stationId);
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/stations/${encodedStationId}/occupancy`);

  if (!response.ok) {
    throw new Error(`Unable to load station occupancy history. Request failed with status ${response.status}`);
  }

  return response.json() as Promise<StationOccupancyApiResponse>;
}
