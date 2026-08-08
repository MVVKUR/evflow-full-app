import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SvgAssetIcon } from '../../shared/SvgAssetIcon';
import type { AggregatedConnectorStatus } from '../station-status/aggregateConnectorStatuses';
import { resolveConnectorEstimate } from '../station-status/aggregateConnectorStatuses';
import { lightningIcon } from './driverMapIcons';

type ConnectorAvailabilityRowProps = { group: AggregatedConnectorStatus };

/** Tinted pill backgrounds with the darker semantic colour as text. */
const pillPalettes = {
  free: { background: '#EAF8F0', text: '#10A957' },
  inUse: { background: '#FFF7ED', text: '#E87500' },
  outOfService: { background: '#F9E9E9', text: '#D64545' },
  unknown: { background: '#F3F5F5', text: '#667176' }
} as const;

type StatusPill = {
  background: string;
  text: string;
  /** The big tabular figure ("1/2", "24 min"); null when the case has no headline number. */
  figure: string | null;
  label: string;
};

export function ConnectorAvailabilityRow({ group }: ConnectorAvailabilityRowProps) {
  const now = useMinuteClock(Boolean(group.earliestEstimate?.availableAt));
  const estimate = group.earliestEstimate?.availableAt
    ? resolveConnectorEstimate({ estimatedWaitMinutes: null, estimatedAvailableAt: group.earliestEstimate.availableAt }, now)
    : group.earliestEstimate;
  const statusText = formatGroupStatus(group, estimate?.minutes ?? null);
  const speed = group.speedTier ? group.speedTier.replace(/_/g, '-').toUpperCase() : 'UNKNOWN SPEED';
  const pill = getStatusPill(group, estimate?.minutes ?? null);

  return (
    <View accessibilityLabel={`${group.connectorType}, ${speed}, ${group.totalCount} plugs. ${statusText}`} accessible style={rowStyles.card}>
      <View accessibilityLabel="Charging connector" accessible style={rowStyles.icon}>
        <SvgAssetIcon color="#007F85" height={18} name="lightning" svg={lightningIcon} width={16} />
      </View>
      <Text numberOfLines={2} style={rowStyles.name}>{group.connectorType} · {speed}</Text>
      <View style={rowStyles.divider} />
      <View style={[rowStyles.pill, { backgroundColor: pill.background }]}>
        {pill.figure !== null ? (
          <Text numberOfLines={1} style={[rowStyles.pillFigure, { color: pill.text }]}>{pill.figure}</Text>
        ) : null}
        <Text numberOfLines={2} style={[rowStyles.pillLabel, { color: pill.text }]}>{pill.label}</Text>
      </View>
    </View>
  );
}

/** Kept as the single source of the row's accessibility sentence. */
export function formatGroupStatus(group: AggregatedConnectorStatus, estimateMinutes: number | null) {
  const parts = [
    group.availableCount ? `${group.availableCount} Available` : null,
    group.occupiedCount ? `${group.occupiedCount} Occupied` : null,
    group.outOfServiceCount ? `${group.outOfServiceCount} Out of Service` : null,
    group.unknownCount ? `${group.unknownCount} Status Unknown` : null
  ].filter((part): part is string => Boolean(part));
  const mixed = parts.length > 1;
  let label = mixed ? parts.join(' · ') : parts[0] ?? 'Status Unknown';
  if (!mixed && group.availableCount === group.totalCount) label = `${group.availableCount} of ${group.totalCount} Available`;
  if (!mixed && group.occupiedCount === 1 && group.totalCount === 1) label = 'In Use';
  if (!mixed && group.outOfServiceCount === 1 && group.totalCount === 1) label = 'Out of Service';
  if (group.availableCount === 0 && group.occupiedCount > 0 && estimateMinutes !== null) {
    label += ` (Est. ${estimateMinutes} ${estimateMinutes === 1 ? 'min' : 'mins'} left)`;
  }
  return label;
}

/**
 * What the pill shows. Each headline figure pairs with its own label so the
 * reading stays unambiguous: "1/2 Available" is free-of-total, "2/2 In Use" is
 * occupied-of-total, "24 min In Use · est. left" is the wait. Mixed groups
 * without an estimate keep the precise sentence as a small-label pill instead
 * of inventing a single number for them.
 */
function getStatusPill(group: AggregatedConnectorStatus, estimateMinutes: number | null): StatusPill {
  const { availableCount, occupiedCount, outOfServiceCount, totalCount } = group;
  if (availableCount > 0) {
    return { ...pillPalettes.free, figure: `${availableCount}/${totalCount}`, label: 'Available' };
  }
  if (occupiedCount > 0 && estimateMinutes !== null) {
    return { ...pillPalettes.inUse, figure: `${estimateMinutes} min`, label: 'In Use · est. left' };
  }
  if (occupiedCount > 0 && occupiedCount === totalCount) {
    return { ...pillPalettes.inUse, figure: totalCount > 1 ? `${occupiedCount}/${totalCount}` : null, label: 'In Use' };
  }
  if (outOfServiceCount > 0 && outOfServiceCount === totalCount) {
    return { ...pillPalettes.outOfService, figure: totalCount > 1 ? `${outOfServiceCount}/${totalCount}` : null, label: 'Out of Service' };
  }
  if (occupiedCount > 0) return { ...pillPalettes.inUse, figure: null, label: formatGroupStatus(group, null) };
  if (outOfServiceCount > 0) return { ...pillPalettes.outOfService, figure: null, label: formatGroupStatus(group, null) };
  return { ...pillPalettes.unknown, figure: null, label: formatGroupStatus(group, null) };
}

function useMinuteClock(enabled: boolean) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    if (!enabled) return;
    const timer = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, [enabled]);
  return now;
}

const rowStyles = StyleSheet.create({
  card: { alignItems: 'center', backgroundColor: '#F6FAFA', borderColor: '#CFE0E1', borderRadius: 12, borderWidth: 1, flexDirection: 'row', minHeight: 40, paddingHorizontal: 12, paddingVertical: 7 },
  icon: { alignItems: 'center', height: 24, justifyContent: 'center', marginRight: 7, width: 20 },
  name: { color: '#263034', flex: 1, fontSize: 11, fontWeight: '900', lineHeight: 15 },
  divider: { backgroundColor: '#D4DEDF', height: 15, marginHorizontal: 10, width: 1 },
  pill: { alignItems: 'center', borderRadius: 999, flexDirection: 'row', flexShrink: 1, gap: 6, justifyContent: 'flex-end', maxWidth: '58%', minHeight: 26, paddingHorizontal: 10, paddingVertical: 3 },
  pillFigure: { fontSize: 18, fontVariant: ['tabular-nums'], fontWeight: '900', lineHeight: 22 },
  pillLabel: { flexShrink: 1, fontSize: 10, fontWeight: '800', lineHeight: 13, textAlign: 'right' }
});
