import { isValidStationLiveStatus, type StationLiveStatus, type StationStatusLoader } from './types';

export type StationStatusRequest = { requestId: number; stationId: string };
export type CachedStationStatus = { data: StationLiveStatus; fetchedAt: number };

export const stationStatusCacheTtlMs = 30_000;

export function getFreshCachedStationStatus(
  cache: Map<string, CachedStationStatus>,
  stationId: string,
  now = Date.now()
) {
  const cached = cache.get(stationId);
  return cached && now - cached.fetchedAt < stationStatusCacheTtlMs ? cached.data : null;
}

export function invalidateCachedStationStatus(cache: Map<string, CachedStationStatus>, stationId: string) {
  cache.delete(stationId);
}

export function isCurrentStationStatusRequest(
  request: StationStatusRequest,
  currentRequestId: number,
  selectedStationId: string | null
) {
  return request.requestId === currentRequestId && request.stationId === selectedStationId;
}

export function shouldRenderSearchBar(drawerMode: 'filter' | 'results' | 'detail') {
  return drawerMode !== 'detail';
}

export function getDrawerModeAfterClosingStationDetail() {
  return 'results' as const;
}

export async function loadValidStationStatus(loader: StationStatusLoader, stationId: string): Promise<StationLiveStatus> {
  const status = await loader(stationId);
  if (!isValidStationLiveStatus(status, stationId)) {
    throw new Error('The station returned an invalid live status response.');
  }
  return status;
}

export function getDrawerAwareMapCenter(
  station: { latitude: number; longitude: number },
  zoom: number,
  coveredHeightPx: number
) {
  const worldSize = 256 * 2 ** zoom;
  const latitudeDegreesPerPixel = (360 * Math.cos((station.latitude * Math.PI) / 180)) / worldSize;
  return {
    latitude: station.latitude - Math.max(0, coveredHeightPx) * latitudeDegreesPerPixel / 2,
    longitude: station.longitude
  };
}
