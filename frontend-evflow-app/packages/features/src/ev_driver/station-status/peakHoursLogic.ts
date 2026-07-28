import type { DailyPeakHours } from './types';

export const peakDayLabels = [
  { dayOfWeek: 1, label: 'Mon', fullLabel: 'Monday' },
  { dayOfWeek: 2, label: 'Tue', fullLabel: 'Tuesday' },
  { dayOfWeek: 3, label: 'Wed', fullLabel: 'Wednesday' },
  { dayOfWeek: 4, label: 'Thu', fullLabel: 'Thursday' },
  { dayOfWeek: 5, label: 'Fri', fullLabel: 'Friday' },
  { dayOfWeek: 6, label: 'Sat', fullLabel: 'Saturday' },
  { dayOfWeek: 0, label: 'Sun', fullLabel: 'Sunday' }
] as const;

export type PeakHourBar = { hour: number; occupancyPercent: number };

export function getJakartaDayAndHour(now: Date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Jakarta',
    weekday: 'short',
    hour: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(now);
  const weekday = parts.find((part) => part.type === 'weekday')?.value;
  const hour = Number(parts.find((part) => part.type === 'hour')?.value ?? 0);
  const day = peakDayLabels.find((item) => item.label === weekday)?.dayOfWeek ?? 1;
  return { dayOfWeek: day, hour };
}

export function createPeakHourBars(day: DailyPeakHours | undefined): PeakHourBar[] {
  return Array.from({ length: 24 }, (_, hour) => ({
    hour,
    occupancyPercent: clampPercent(day?.hourlyOccupancyPercent[hour] ?? 0)
  }));
}

export function selectPeakHoursDay(days: DailyPeakHours[], requestedDay: number) {
  return days.find((day) => day.dayOfWeek === requestedDay) ?? days[0];
}

export function getLowDemandRecommendation(values: number[]) {
  if (values.length !== 24) return 'Best times to visit: live pattern unavailable';
  const sorted = [...values].sort((left, right) => left - right);
  const threshold = Math.max(30, sorted[7]);
  const lowHours = values.map((value, hour) => value <= threshold ? hour : -1).filter((hour) => hour >= 0);
  const ranges: Array<{ start: number; end: number }> = [];
  lowHours.forEach((hour) => {
    const lastRange = ranges[ranges.length - 1];
    if (lastRange && hour === lastRange.end + 1) lastRange.end = hour;
    else ranges.push({ start: hour, end: hour });
  });
  const bestRanges = ranges
    .sort((left, right) => (right.end - right.start) - (left.end - left.start))
    .slice(0, 2)
    .sort((left, right) => left.start - right.start);
  return `Best times to visit: ${bestRanges.map(formatRange).join(' or ')}`;
}

export function getLiveComparison(
  livePercent: number | null,
  typicalPercent: number,
  dayName: string
) {
  if (livePercent === null) return 'Live now: current occupancy is unavailable';
  if (livePercent <= typicalPercent - 10) return 'Live now: quieter than usual, a good time to charge';
  if (livePercent >= typicalPercent + 10) return `Live now: busier than usual for a ${dayName}`;
  return `Live now: about as busy as usual for a ${dayName}`;
}

function formatRange(range: { start: number; end: number }) {
  if (range.start === 0) return `before ${formatHour(range.end + 1)}`;
  if (range.end === 23) return `after ${formatHour(range.start)}`;
  return `${formatHour(range.start)}–${formatHour(range.end + 1)}`;
}

function formatHour(hour: number) {
  const normalized = hour % 24;
  if (normalized === 0) return '12am';
  if (normalized === 12) return '12pm';
  return normalized < 12 ? `${normalized}am` : `${normalized - 12}pm`;
}

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, value));
}
