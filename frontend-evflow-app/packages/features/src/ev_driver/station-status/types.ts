export type ConnectorOperationalStatus =
  | 'available'
  | 'occupied'
  | 'out_of_service'
  | 'unknown';

export type LiveConnectorStatus = {
  connectorId: string;
  connectorType: string;
  speedTier: string | null;
  powerKw: number | null;
  status: ConnectorOperationalStatus;
  estimatedWaitMinutes: number | null;
  estimatedAvailableAt: string | null;
};

export type DailyPeakHours = {
  dayOfWeek: number;
  hourlyOccupancyPercent: number[];
};

export type StationLiveStatus = {
  stationId: string;
  observedAt: string;
  connectors: LiveConnectorStatus[];
  peakHours: {
    timezone: 'Asia/Jakarta';
    days: DailyPeakHours[];
    currentOccupancyPercent: number | null;
  };
};

export type StationStatusLoader = (stationId: string) => Promise<StationLiveStatus>;

const operationalStatuses = new Set<ConnectorOperationalStatus>([
  'available',
  'occupied',
  'out_of_service',
  'unknown'
]);

export function isValidStationLiveStatus(value: unknown, requestedStationId?: string): value is StationLiveStatus {
  if (!value || typeof value !== 'object') {
    return false;
  }

  const status = value as StationLiveStatus;
  if (
    typeof status.stationId !== 'string' ||
    status.stationId.length === 0 ||
    (requestedStationId !== undefined && status.stationId !== requestedStationId) ||
    typeof status.observedAt !== 'string' ||
    !Number.isFinite(Date.parse(status.observedAt)) ||
    !Array.isArray(status.connectors) ||
    !status.peakHours ||
    status.peakHours.timezone !== 'Asia/Jakarta' ||
    !Array.isArray(status.peakHours.days) ||
    status.peakHours.days.length !== 7
  ) {
    return false;
  }

  const validConnectors = status.connectors.every((connector) =>
    Boolean(connector) &&
    typeof connector.connectorId === 'string' &&
    typeof connector.connectorType === 'string' &&
    operationalStatuses.has(connector.status) &&
    (connector.speedTier === null || typeof connector.speedTier === 'string') &&
    (connector.powerKw === null || (typeof connector.powerKw === 'number' && Number.isFinite(connector.powerKw) && connector.powerKw >= 0)) &&
    (connector.estimatedWaitMinutes === null || (typeof connector.estimatedWaitMinutes === 'number' && Number.isFinite(connector.estimatedWaitMinutes) && connector.estimatedWaitMinutes >= 0)) &&
    (connector.estimatedAvailableAt === null || (typeof connector.estimatedAvailableAt === 'string' && Number.isFinite(Date.parse(connector.estimatedAvailableAt))))
  );

  const seenDays = new Set<number>();
  const validDays = status.peakHours.days.every((day) => {
    if (
      !Number.isInteger(day.dayOfWeek) ||
      day.dayOfWeek < 0 ||
      day.dayOfWeek > 6 ||
      seenDays.has(day.dayOfWeek) ||
      !Array.isArray(day.hourlyOccupancyPercent) ||
      day.hourlyOccupancyPercent.length !== 24 ||
      !day.hourlyOccupancyPercent.every((percent) => typeof percent === 'number' && Number.isFinite(percent) && percent >= 0 && percent <= 100)
    ) {
      return false;
    }
    seenDays.add(day.dayOfWeek);
    return true;
  });

  return validConnectors && validDays &&
    (status.peakHours.currentOccupancyPercent === null ||
      (typeof status.peakHours.currentOccupancyPercent === 'number' &&
        status.peakHours.currentOccupancyPercent >= 0 &&
        status.peakHours.currentOccupancyPercent <= 100));
}
