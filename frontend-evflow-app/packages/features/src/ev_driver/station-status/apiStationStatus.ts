import {
  fetchStationOccupancy,
  fetchStationStatus,
  type StationOccupancyApiResponse,
  type StationStatusApiResponse
} from '@evflow/shared';
import { isValidStationLiveStatus, type DailyPeakHours, type LiveConnectorStatus, type StationLiveStatus } from './types';

const backendDaysMondayThroughSunday = [1, 2, 3, 4, 5, 6, 7] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object';
}

function isStationStatusResponse(value: unknown): value is StationStatusApiResponse {
  if (!isRecord(value) || !Array.isArray(value.connectors)) {
    return false;
  }

  return typeof value.station_id === 'string' &&
    typeof value.station_status === 'number' &&
    typeof value.available === 'string' &&
    typeof value.total === 'string' &&
    typeof value.waiting_time === 'number' &&
    value.connectors.every((connector) =>
      isRecord(connector) &&
      typeof connector.type === 'string' &&
      (connector.speed_tier === null || typeof connector.speed_tier === 'string') &&
      typeof connector.available === 'string' &&
      typeof connector.total === 'string' &&
      typeof connector.waiting_time === 'string'
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
      typeof hour.avg_occupancy === 'number'
    )
  );
}

function parseNonNegativeNumber(value: unknown) {
  const parsed = typeof value === 'number'
    ? value
    : typeof value === 'string' && value.trim().length > 0
      ? Number(value)
      : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

function parseCount(value: unknown) {
  return Math.floor(parseNonNegativeNumber(value));
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum);
}

function expandConnectors(stationId: string, response: StationStatusApiResponse): LiveConnectorStatus[] {
  const stationWaitingTime = parseNonNegativeNumber(response.waiting_time);
  let connectorIndex = 0;

  return response.connectors.flatMap((connector) => {
    const totalCount = parseCount(connector.total);
    const availableCount = Math.min(parseCount(connector.available), totalCount);
    const occupiedCount = Math.max(totalCount - availableCount, 0);
    const connectorType = connector.type || 'Unknown connector';
    const groupWaitingTime = parseNonNegativeNumber(connector.waiting_time);
    const occupiedWaitingTime = groupWaitingTime > 0 ? groupWaitingTime : stationWaitingTime;
    const createConnector = (status: LiveConnectorStatus['status'], estimatedWaitMinutes: number | null) => {
      const result: LiveConnectorStatus = {
        connectorId: `${stationId}:${connectorType}:${connector.speed_tier ?? 'unknown'}:${connectorIndex}`,
        connectorType,
        speedTier: connector.speed_tier,
        powerKw: null,
        status,
        estimatedWaitMinutes,
        estimatedAvailableAt: null
      };
      connectorIndex += 1;
      return result;
    };

    return [
      ...Array.from({ length: availableCount }, () => createConnector('available', null)),
      ...Array.from({ length: occupiedCount }, () => createConnector('occupied', occupiedWaitingTime))
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
        day.hourlyOccupancyPercent[hour.hour_of_day] = clamp(parseNonNegativeNumber(hour.avg_occupancy), 0, 100);
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

  const total = parseCount(statusResponse.total);
  const available = Math.min(parseCount(statusResponse.available), total);
  const currentOccupancyPercent = total > 0
    ? clamp(Math.round(((total - available) / total) * 100), 0, 100)
    : null;
  const liveStatus: StationLiveStatus = {
    stationId,
    observedAt: new Date().toISOString(),
    connectors: expandConnectors(stationId, statusResponse),
    peakHours: {
      timezone: 'Asia/Jakarta',
      days: buildPeakHourDays(occupancyResponse),
      currentOccupancyPercent
    }
  };

  if (!isValidStationLiveStatus(liveStatus, stationId)) {
    throw new Error('The station returned an invalid live status response.');
  }
  return liveStatus;
}
