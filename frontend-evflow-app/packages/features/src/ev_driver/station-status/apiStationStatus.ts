import {
  fetchStationOccupancy,
  fetchStationStatus,
  type StationOccupancyApiResponse,
  type StationOccupancyLevel,
  type StationStatusApiResponse
} from '@evflow/shared';
import { isValidStationLiveStatus, type DailyPeakHours, type LiveConnectorStatus, type StationLiveStatus } from './types';

const backendDaysMondayThroughSunday = [1, 2, 3, 4, 5, 6, 7] as const;

const occupancyLevels = new Set<StationOccupancyLevel>(['LOW', 'MODERATE', 'BUSY', 'PEAK']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object';
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

/** Minutes, or null when the backend has no estimate. Never a string. */
function isWaitingTime(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0);
}

function isStationStatusResponse(value: unknown): value is StationStatusApiResponse {
  if (!isRecord(value) || !Array.isArray(value.connectors)) {
    return false;
  }

  return typeof value.station_id === 'string' &&
    typeof value.station_status === 'number' &&
    isCount(value.available) &&
    isCount(value.total) &&
    isCount(value.in_use) &&
    isCount(value.out_of_service) &&
    isWaitingTime(value.waiting_time) &&
    value.connectors.every((connector) =>
      isRecord(connector) &&
      typeof connector.type === 'string' &&
      (connector.speed_tier === null || typeof connector.speed_tier === 'string') &&
      (connector.power_kw === null || (typeof connector.power_kw === 'number' && Number.isFinite(connector.power_kw) && connector.power_kw >= 0)) &&
      isCount(connector.available) &&
      isCount(connector.total) &&
      isCount(connector.in_use) &&
      isCount(connector.out_of_service) &&
      isWaitingTime(connector.waiting_time)
    );
}

function isStationOccupancyResponse(value: unknown): value is StationOccupancyApiResponse {
  if (!isRecord(value) || typeof value.station_id !== 'string' || !Array.isArray(value.days)) {
    return false;
  }

  return value.days.every((day) =>
    isRecord(day) &&
    typeof day.day_of_week === 'number' &&
    typeof day.day_name === 'string' &&
    Array.isArray(day.hours) &&
    day.hours.every((hour) =>
      isRecord(hour) &&
      typeof hour.hour_of_day === 'number' &&
      typeof hour.avg_occupancy === 'number' &&
      Number.isFinite(hour.avg_occupancy) &&
      occupancyLevels.has(hour.occupancy_level as StationOccupancyLevel)
    )
  );
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum);
}

function expandConnectors(stationId: string, response: StationStatusApiResponse): LiveConnectorStatus[] {
  let connectorIndex = 0;

  return response.connectors.flatMap((connector) => {
    const connectorType = connector.type || 'Unknown connector';
    // The wait applies only to plugs that will actually free up. Falling back to
    // the station-wide figure would attach one group's estimate to another's.
    const occupiedWaitMinutes = connector.waiting_time ?? response.waiting_time;
    const createConnector = (status: LiveConnectorStatus['status'], estimatedWaitMinutes: number | null) => {
      const result: LiveConnectorStatus = {
        connectorId: `${stationId}:${connectorType}:${connector.speed_tier ?? 'unknown'}:${connectorIndex}`,
        connectorType,
        speedTier: connector.speed_tier,
        powerKw: connector.power_kw,
        status,
        estimatedWaitMinutes,
        estimatedAvailableAt: null
      };
      connectorIndex += 1;
      return result;
    };

    // out_of_service is kept apart from in_use on purpose: a broken plug is not
    // going to free up, so it must never carry a wait estimate.
    return [
      ...Array.from({ length: connector.available }, () => createConnector('available', null)),
      ...Array.from({ length: connector.in_use }, () => createConnector('occupied', occupiedWaitMinutes)),
      ...Array.from({ length: connector.out_of_service }, () => createConnector('out_of_service', null))
    ];
  });
}

function buildPeakHourDays(response: StationOccupancyApiResponse): DailyPeakHours[] {
  const days = new Map<number, DailyPeakHours>(
    backendDaysMondayThroughSunday.map((backendDayOfWeek) => {
      const frontendDayOfWeek = backendDayOfWeek % 7;
      return [frontendDayOfWeek, {
        dayOfWeek: frontendDayOfWeek,
        hourlyOccupancyPercent: Array<number>(24).fill(0)
      }];
    })
  );

  response.days.forEach((apiDay) => {
    if (!Number.isInteger(apiDay.day_of_week) || apiDay.day_of_week < 1 || apiDay.day_of_week > 7) {
      return;
    }

    const day = days.get(apiDay.day_of_week % 7);
    apiDay.hours.forEach((hour) => {
      if (day && Number.isInteger(hour.hour_of_day) && hour.hour_of_day >= 0 && hour.hour_of_day <= 23) {
        day.hourlyOccupancyPercent[hour.hour_of_day] = clamp(hour.avg_occupancy, 0, 100);
      }
    });
  });

  return backendDaysMondayThroughSunday.map((backendDayOfWeek) => days.get(backendDayOfWeek % 7)!);
}

export async function getApiStationLiveStatus(
  stationId: string,
  fetcher: typeof fetch = fetch
): Promise<StationLiveStatus> {
  const [statusResponse, occupancyResponse] = await Promise.all([
    fetchStationStatus(stationId, fetcher),
    fetchStationOccupancy(stationId, fetcher)
  ]);

  if (isRecord(statusResponse) && typeof statusResponse.station_id === 'string' && statusResponse.station_id !== stationId) {
    throw new Error('The station status response does not match the selected station.');
  }
  if (isRecord(occupancyResponse) && typeof occupancyResponse.station_id === 'string' && occupancyResponse.station_id !== stationId) {
    throw new Error('The station occupancy response does not match the selected station.');
  }
  if (!isStationStatusResponse(statusResponse) || !isStationOccupancyResponse(occupancyResponse)) {
    throw new Error('The station returned an invalid live status response.');
  }

  // Counted over every connector, matching the denominator the backend uses for
  // the historical avg_occupancy this gets compared against. Broken plugs are
  // excluded from the numerator: unusable is not the same as busy.
  const currentOccupancyPercent = statusResponse.total > 0
    ? clamp(Math.round((statusResponse.in_use / statusResponse.total) * 100), 0, 100)
    : null;
  const liveStatus: StationLiveStatus = {
    stationId,
    observedAt: new Date().toISOString(),
    connectors: expandConnectors(stationId, statusResponse),
    peakHours: {
      timezone: 'Asia/Jakarta',
      days: buildPeakHourDays(occupancyResponse),
      currentOccupancyPercent,
      // An empty days array means the backend has no history for this station.
      // The zero-filled week below is scaffolding for the chart's layout, not
      // measurements, and must not be presented as such.
      hasHistory: occupancyResponse.days.length > 0
    }
  };

  if (!isValidStationLiveStatus(liveStatus, stationId)) {
    throw new Error('The station returned an invalid live status response.');
  }
  return liveStatus;
}
