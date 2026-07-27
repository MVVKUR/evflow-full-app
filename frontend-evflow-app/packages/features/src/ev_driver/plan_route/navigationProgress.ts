import type { RouteStep } from '@evflow/shared';

export type Point = { latitude: number; longitude: number };
export type RouteMatch = Point & {
  distanceM: number;
  travelledM: number;
  totalM: number;
  remainingM: number;
  point: Point;
};

const earthRadiusM = 6371008.8;
const radians = (value: number) => value * Math.PI / 180;

export function distanceMeters(a: Point, b: Point): number {
  const dLat = radians(b.latitude - a.latitude);
  const dLon = radians(b.longitude - a.longitude);
  const value = Math.sin(dLat / 2) ** 2
    + Math.cos(radians(a.latitude)) * Math.cos(radians(b.latitude)) * Math.sin(dLon / 2) ** 2;
  return 2 * earthRadiusM * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
}

function project(point: Point, a: Point, b: Point) {
  const latScale = 111320;
  const lonScale = latScale * Math.cos(radians(a.latitude));
  const px = (point.longitude - a.longitude) * lonScale;
  const py = (point.latitude - a.latitude) * latScale;
  const bx = (b.longitude - a.longitude) * lonScale;
  const by = (b.latitude - a.latitude) * latScale;
  const denominator = bx * bx + by * by;
  const t = denominator ? Math.max(0, Math.min(1, (px * bx + py * by) / denominator)) : 0;
  return {
    point: {
      latitude: a.latitude + (b.latitude - a.latitude) * t,
      longitude: a.longitude + (b.longitude - a.longitude) * t,
    },
    t,
  };
}

export function matchRoute(point: Point, line: [number, number][]): RouteMatch {
  let best = { distanceM: Infinity, travelledM: 0, point };
  let before = 0;
  for (let index = 1; index < line.length; index += 1) {
    const a = { latitude: line[index - 1][1], longitude: line[index - 1][0] };
    const b = { latitude: line[index][1], longitude: line[index][0] };
    const segmentM = distanceMeters(a, b);
    const hit = project(point, a, b);
    const distanceM = distanceMeters(point, hit.point);
    if (distanceM < best.distanceM) {
      best = { distanceM, travelledM: before + segmentM * hit.t, point: hit.point };
    }
    before += segmentM;
  }
  return { ...best, ...best.point, totalM: before, remainingM: Math.max(0, before - best.travelledM) };
}

export function maneuverDistances(steps: RouteStep[], line: [number, number][]): number[] {
  return steps.map((step, index) => {
    if (!step.location || step.location.length < 2 || line.length < 2) return index === 0 ? 0 : Infinity;
    return matchRoute({ latitude: step.location[1], longitude: step.location[0] }, line).travelledM;
  });
}

export function advanceStep(
  steps: RouteStep[],
  index: number,
  matched: Point,
  travelledM = 0,
  alongRoute = maneuverDistances(steps, []),
  thresholdM = 35,
): number {
  let next = index;
  while (next < steps.length - 1) {
    const upcoming = steps[next + 1];
    const location = upcoming.location;
    const enteredThreshold = Boolean(location)
      && distanceMeters(matched, { latitude: location![1], longitude: location![0] }) <= thresholdM;
    const crossedProgress = Number.isFinite(alongRoute[next + 1])
      && travelledM + thresholdM >= alongRoute[next + 1];
    if (!enteredThreshold && !crossedProgress) break;
    next += 1;
  }
  return next;
}

export function nextManeuverDistanceM(index: number, travelledM: number, alongRoute: number[]): number {
  const nextDistance = alongRoute[Math.min(index + 1, alongRoute.length - 1)];
  return Number.isFinite(nextDistance) ? Math.max(0, nextDistance - travelledM) : 0;
}

export function isOffRoute(consecutiveInvalidFixes: number): boolean {
  return consecutiveInvalidFixes >= 3;
}

export function monotonicDistance(previousKm: number, candidateKm: number): number {
  return Math.max(previousKm, candidateKm);
}
