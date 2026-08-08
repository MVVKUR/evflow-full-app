export type StationAvailabilityBand = 'free' | 'limited' | 'full' | 'unknown';

/** Pin colours. Deliberately the same greens and reds as the peak-hours chart. */
export const stationBandColors: Record<StationAvailabilityBand, string> = {
  free: '#10A957',
  limited: '#F0B429',
  full: '#D64545',
  unknown: '#007a80'
};

export const stationBandLabels: Record<StationAvailabilityBand, string> = {
  free: 'plugs free',
  limited: 'almost full',
  full: 'full',
  unknown: 'availability unknown'
};

/**
 * Which colour a station pin gets.
 *
 * The driver's question at a pin is "can I charge there right now?", so the
 * bands are cut around that rather than around a tidy percentage:
 *
 *   full    — nothing free. Not "busy": there is no plug to take.
 *   limited — something free, but a third or less of the station.
 *   free    — comfortably available.
 *   unknown — the counts are absent. A station with no connectors on record is
 *             also unknown, NOT full: we would be claiming a fact we do not have.
 */
export function getStationAvailabilityBand(
  available: number | null | undefined,
  total: number | null | undefined
): StationAvailabilityBand {
  if (typeof available !== 'number' || typeof total !== 'number' || total <= 0) {
    return 'unknown';
  }
  if (available <= 0) return 'full';
  return available / total <= 1 / 3 ? 'limited' : 'free';
}
