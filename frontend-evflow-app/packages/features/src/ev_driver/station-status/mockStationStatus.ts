import type { DailyPeakHours, StationLiveStatus, StationStatusLoader } from './types';

const weekdayProfiles: Record<number, number[]> = {
  1: [8, 6, 5, 5, 7, 14, 28, 46, 62, 54, 42, 36, 32, 38, 48, 57, 68, 82, 88, 76, 54, 34, 20, 12],
  2: [7, 6, 5, 5, 8, 16, 30, 49, 65, 58, 44, 38, 34, 40, 50, 60, 72, 84, 91, 79, 58, 36, 21, 13],
  3: [8, 7, 6, 5, 8, 17, 31, 50, 66, 59, 46, 39, 35, 42, 53, 63, 74, 86, 93, 81, 60, 38, 22, 14],
  4: [9, 7, 6, 6, 9, 18, 33, 52, 68, 61, 48, 41, 37, 44, 55, 65, 76, 88, 95, 83, 62, 40, 24, 15],
  5: [10, 8, 7, 6, 10, 20, 35, 54, 70, 64, 51, 44, 40, 47, 58, 69, 80, 91, 97, 87, 68, 46, 28, 18],
  6: [14, 11, 9, 8, 10, 17, 25, 36, 48, 58, 66, 72, 75, 78, 81, 84, 87, 89, 85, 76, 62, 45, 31, 21],
  0: [13, 10, 8, 7, 9, 15, 22, 32, 43, 53, 61, 67, 70, 73, 76, 79, 82, 84, 80, 71, 57, 41, 28, 19]
};

const peakDays: DailyPeakHours[] = [1, 2, 3, 4, 5, 6, 0].map((dayOfWeek) => ({
  dayOfWeek,
  hourlyOccupancyPercent: [...weekdayProfiles[dayOfWeek]]
}));

export const availableStationStatusFixture: StationLiveStatus = {
  stationId: 'fixture-available',
  observedAt: '2026-07-28T14:20:00+07:00',
  connectors: [
    { connectorId: 'a-ccs-1', connectorType: 'CCS2', speedTier: 'ultra_fast', powerKw: 180, status: 'available', estimatedWaitMinutes: null, estimatedAvailableAt: null },
    { connectorId: 'a-ccs-2', connectorType: 'CCS2', speedTier: 'ultra_fast', powerKw: 180, status: 'available', estimatedWaitMinutes: null, estimatedAvailableAt: null },
    { connectorId: 'a-ccs-3', connectorType: 'CCS2', speedTier: 'ultra_fast', powerKw: 180, status: 'out_of_service', estimatedWaitMinutes: null, estimatedAvailableAt: null },
    { connectorId: 'a-type2-1', connectorType: 'Type 2', speedTier: 'slow', powerKw: 22, status: 'occupied', estimatedWaitMinutes: 15, estimatedAvailableAt: '2026-07-28T14:35:00+07:00' },
    { connectorId: 'a-chademo-1', connectorType: 'CHAdeMO', speedTier: 'fast', powerKw: 60, status: 'available', estimatedWaitMinutes: null, estimatedAvailableAt: null }
  ],
  peakHours: { timezone: 'Asia/Jakarta', days: peakDays, currentOccupancyPercent: 46 }
};

export const occupiedStationStatusFixture: StationLiveStatus = {
  stationId: 'fixture-occupied',
  observedAt: '2026-07-28T14:20:00+07:00',
  connectors: [
    { connectorId: 'o-ccs-1', connectorType: 'CCS2', speedTier: 'ultra_fast', powerKw: 180, status: 'occupied', estimatedWaitMinutes: 8, estimatedAvailableAt: '2026-07-28T14:28:00+07:00' },
    { connectorId: 'o-ccs-2', connectorType: 'CCS2', speedTier: 'ultra_fast', powerKw: 180, status: 'occupied', estimatedWaitMinutes: 19, estimatedAvailableAt: '2026-07-28T14:39:00+07:00' },
    { connectorId: 'o-ccs-3', connectorType: 'CCS2', speedTier: 'ultra_fast', powerKw: 180, status: 'occupied', estimatedWaitMinutes: 26, estimatedAvailableAt: '2026-07-28T14:46:00+07:00' },
    { connectorId: 'o-type2-1', connectorType: 'Type 2', speedTier: 'slow', powerKw: 22, status: 'occupied', estimatedWaitMinutes: 15, estimatedAvailableAt: '2026-07-28T14:35:00+07:00' },
    { connectorId: 'o-type2-2', connectorType: 'Type 2', speedTier: 'slow', powerKw: 22, status: 'occupied', estimatedWaitMinutes: 31, estimatedAvailableAt: '2026-07-28T14:51:00+07:00' },
    { connectorId: 'o-chademo-1', connectorType: 'CHAdeMO', speedTier: 'fast', powerKw: 60, status: 'occupied', estimatedWaitMinutes: 12, estimatedAvailableAt: '2026-07-28T14:32:00+07:00' }
  ],
  peakHours: { timezone: 'Asia/Jakarta', days: peakDays, currentOccupancyPercent: 100 }
};

/** Temporary integration boundary. Replace this import at DriverMapScreen when the shared API loader lands. */
export const getMockStationLiveStatus: StationStatusLoader = async (stationId) => {
  const checksum = Array.from(stationId).reduce((total, character) => total + character.charCodeAt(0), 0);
  const fixture = checksum % 2 === 0 ? availableStationStatusFixture : occupiedStationStatusFixture;
  return {
    ...fixture,
    stationId,
    connectors: fixture.connectors.map((connector) => ({ ...connector })),
    peakHours: {
      ...fixture.peakHours,
      days: fixture.peakHours.days.map((day) => ({ ...day, hourlyOccupancyPercent: [...day.hourlyOccupancyPercent] }))
    }
  };
};
