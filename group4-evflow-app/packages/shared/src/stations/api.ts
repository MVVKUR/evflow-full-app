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
