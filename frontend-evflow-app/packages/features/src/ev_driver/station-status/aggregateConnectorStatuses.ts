import type { ConnectorOperationalStatus, LiveConnectorStatus } from './types';

export type AvailabilityState = 'available' | 'occupied' | 'out_of_service' | 'unknown';

export type AvailabilityEstimate = {
  availableAt: string | null;
  minutes: number;
};

export type AggregatedConnectorStatus = {
  key: string;
  connectorType: string;
  speedTier: string | null;
  powerKw: number | null;
  totalCount: number;
  availableCount: number;
  occupiedCount: number;
  outOfServiceCount: number;
  unknownCount: number;
  earliestEstimate: AvailabilityEstimate | null;
};

export type StationAvailability = {
  state: AvailabilityState;
  title: string;
  subtitle: string;
  totalCount: number;
  availableCount: number;
  occupiedCount: number;
  outOfServiceCount: number;
  unknownCount: number;
  earliestEstimate: AvailabilityEstimate | null;
  groups: AggregatedConnectorStatus[];
};

export function aggregateConnectorStatuses(
  connectors: LiveConnectorStatus[],
  now: Date = new Date()
): StationAvailability {
  const groupsByKey = new Map<string, AggregatedConnectorStatus>();

  connectors.forEach((connector) => {
    const key = `${connector.connectorType}\u0000${connector.speedTier ?? ''}`;
    const group = groupsByKey.get(key) ?? {
      key,
      connectorType: connector.connectorType || 'Unknown connector',
      speedTier: connector.speedTier,
      powerKw: connector.powerKw,
      totalCount: 0,
      availableCount: 0,
      occupiedCount: 0,
      outOfServiceCount: 0,
      unknownCount: 0,
      earliestEstimate: null
    };

    group.totalCount += 1;
    group.powerKw = group.powerKw ?? connector.powerKw;
    incrementStatusCount(group, connector.status);

    if (connector.status === 'occupied') {
      const estimate = resolveConnectorEstimate(connector, now);
      if (estimate && (!group.earliestEstimate || estimate.minutes < group.earliestEstimate.minutes)) {
        group.earliestEstimate = estimate;
      }
    }
    groupsByKey.set(key, group);
  });

  const groups = Array.from(groupsByKey.values());
  const counts = groups.reduce(
    (total, group) => ({
      totalCount: total.totalCount + group.totalCount,
      availableCount: total.availableCount + group.availableCount,
      occupiedCount: total.occupiedCount + group.occupiedCount,
      outOfServiceCount: total.outOfServiceCount + group.outOfServiceCount,
      unknownCount: total.unknownCount + group.unknownCount
    }),
    { totalCount: 0, availableCount: 0, occupiedCount: 0, outOfServiceCount: 0, unknownCount: 0 }
  );
  const earliestEstimate = groups.reduce<AvailabilityEstimate | null>(
    (earliest, group) => group.earliestEstimate && (!earliest || group.earliestEstimate.minutes < earliest.minutes)
      ? group.earliestEstimate
      : earliest,
    null
  );
  const state = resolveAvailabilityState(counts);

  return {
    ...counts,
    state,
    earliestEstimate,
    groups,
    ...getAvailabilityCopy(state, counts.availableCount, counts.totalCount, earliestEstimate)
  };
}

export function resolveConnectorEstimate(
  connector: Pick<LiveConnectorStatus, 'estimatedWaitMinutes' | 'estimatedAvailableAt'>,
  now: Date = new Date()
): AvailabilityEstimate | null {
  if (typeof connector.estimatedWaitMinutes === 'number' && Number.isFinite(connector.estimatedWaitMinutes)) {
    return { availableAt: null, minutes: Math.max(0, Math.ceil(connector.estimatedWaitMinutes)) };
  }

  if (connector.estimatedAvailableAt) {
    const timestamp = Date.parse(connector.estimatedAvailableAt);
    if (Number.isFinite(timestamp)) {
      return {
        availableAt: connector.estimatedAvailableAt,
        minutes: Math.max(0, Math.ceil((timestamp - now.getTime()) / 60_000))
      };
    }
  }

  return null;
}

function incrementStatusCount(group: AggregatedConnectorStatus, status: ConnectorOperationalStatus) {
  if (status === 'available') group.availableCount += 1;
  else if (status === 'occupied') group.occupiedCount += 1;
  else if (status === 'out_of_service') group.outOfServiceCount += 1;
  else group.unknownCount += 1;
}

function resolveAvailabilityState(counts: Omit<StationAvailability, 'state' | 'title' | 'subtitle' | 'earliestEstimate' | 'groups'>): AvailabilityState {
  if (counts.availableCount > 0) return 'available';
  if (counts.occupiedCount > 0) return 'occupied';
  if (counts.outOfServiceCount > 0 && counts.availableCount === 0 && counts.occupiedCount === 0) {
    return 'out_of_service';
  }
  return 'unknown';
}

function getAvailabilityCopy(
  state: AvailabilityState,
  availableCount: number,
  totalCount: number,
  estimate: AvailabilityEstimate | null
) {
  if (state === 'available') {
    return { title: 'Chargers Available', subtitle: `${availableCount} of ${totalCount} connectors available right now` };
  }
  if (state === 'occupied') {
    return {
      title: 'Currently Occupied',
      subtitle: estimate ? `Est. ~${estimate.minutes} ${estimate.minutes === 1 ? 'min' : 'mins'} left` : 'All working connectors are currently in use'
    };
  }
  if (state === 'out_of_service') {
    return { title: 'Temporarily Unavailable', subtitle: 'All connectors are currently out of service' };
  }
  return { title: 'Live Status Unavailable', subtitle: 'Try refreshing the station status' };
}
