export function formatDistance(km: number): string {
  if (km < 1) {
    return `${Math.round(km * 1000)} m`;
  }
  return `${Math.round(km)} km`;
}

export function formatDuration(mins: number): string {
  const totalMins = Math.round(mins);
  if (totalMins < 60) {
    return `${totalMins}m`;
  }
  const hours = Math.floor(totalMins / 60);
  const remainingMins = totalMins % 60;
  const formattedMins = remainingMins < 10 ? `0${remainingMins}` : `${remainingMins}`;
  return `${hours}h ${formattedMins}m`;
}

export function formatEnergy(kwh: number): string {
  return `${kwh.toFixed(1)} kWh`;
}

export function formatSoc(pct: number): string {
  return `${Math.round(pct)}%`;
}

export function formatEta(durationMins: number): string {
  const now = new Date();
  const arrival = new Date(now.getTime() + durationMins * 60 * 1000);
  const hours = arrival.getHours().toString().padStart(2, '0');
  const minutes = arrival.getMinutes().toString().padStart(2, '0');
  return `${hours}:${minutes}`;
}
