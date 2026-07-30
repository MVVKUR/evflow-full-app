import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SvgAssetIcon } from '../../shared/SvgAssetIcon';
import type { AggregatedConnectorStatus } from '../station-status/aggregateConnectorStatuses';
import { resolveConnectorEstimate } from '../station-status/aggregateConnectorStatuses';
import { lightningIcon } from './driverMapIcons';

type ConnectorAvailabilityRowProps = { group: AggregatedConnectorStatus };

export function ConnectorAvailabilityRow({ group }: ConnectorAvailabilityRowProps) {
  const now = useMinuteClock(Boolean(group.earliestEstimate?.availableAt));
  const estimate = group.earliestEstimate?.availableAt
    ? resolveConnectorEstimate({ estimatedWaitMinutes: null, estimatedAvailableAt: group.earliestEstimate.availableAt }, now)
    : group.earliestEstimate;
  const statusText = formatGroupStatus(group, estimate?.minutes ?? null);
  const speed = group.speedTier ? group.speedTier.replace(/_/g, '-').toUpperCase() : 'UNKNOWN SPEED';
  const statusColor = group.availableCount > 0 ? '#0A9F4F' : group.occupiedCount > 0 ? '#E87500' : '#667176';

  return (
    <View accessibilityLabel={`${group.connectorType}, ${speed}, ${group.totalCount} plugs. ${statusText}`} accessible style={rowStyles.card}>
      <View accessibilityLabel="Charging connector" accessible style={rowStyles.icon}>
        <SvgAssetIcon color="#007F85" height={18} name="lightning" svg={lightningIcon} width={16} />
      </View>
      <Text numberOfLines={2} style={rowStyles.name}>{group.connectorType} · {speed}</Text>
      <View style={rowStyles.divider} />
      <Text numberOfLines={2} style={[rowStyles.status, { color: statusColor }]}>{statusText}</Text>
    </View>
  );
}

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
  status: { flexShrink: 1, fontSize: 11, fontWeight: '900', lineHeight: 15, maxWidth: '58%', textAlign: 'right' }
});
