import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import type { RecommendedStop } from '@evflow/shared';
import { formatDistance, formatEnergy, formatSoc } from './planRouteUtils';
import { MetricValueText } from './components/MetricValueText';
import { routeColors, routeRadius, routeSpacing } from './routeTheme';

export function ChargingStopCard({ stop, onAddStop, added = false, busy = false, actionLabel = 'Add stop to route' }: { stop: RecommendedStop; onAddStop?: () => void; added?: boolean; busy?: boolean; actionLabel?: string }) {
  const rawConnector = stop.matched_connector_type ?? stop.station.connector_types?.[0];
  const connector = typeof rawConnector === 'string' ? rawConnector : rawConnector?.type;
  const power = stop.best_available_power_kw ?? stop.effective_charging_power_kw ?? stop.station.power_kw;
  return <View style={styles.card}>
    <View style={styles.header}><View style={styles.copy}><Text style={styles.name} numberOfLines={2}>{stop.station.name || 'Charging station'}</Text><Text style={styles.address} numberOfLines={2}>{stop.station.address || stop.station.city || 'Address unavailable'}</Text></View><View style={styles.distancePill}><MetricValueText value={`${formatDistance(stop.distance_from_origin_km)} in`} numberStyle={styles.distanceNumber} unitStyle={styles.distanceUnit} /></View></View>
    <View style={styles.pills}>{connector ? <InfoPill text={connector} /> : null}{power != null ? <InfoPill text={`${Math.round(power)} kW`} /> : null}<InfoPill success text={stop.available_connector_count != null ? `${stop.available_connector_count} available` : stop.availability.split('_').join(' ')} /></View>
    <View style={styles.evidence}><Evidence label="Detour" value={formatDistance(stop.detour_km)} /><Evidence label="Arrival at station" value={formatSoc(stop.arrival_soc_pct)} /><Evidence label="Charge target" value={formatSoc(stop.recommended_target_soc_pct)} /><Evidence label="Charging time" value={`${Math.round(stop.estimated_charging_minutes)} min`} /><Evidence label="Energy added" value={formatEnergy(stop.energy_to_add_kwh)} /></View>
    <Text style={styles.rank}>Server-ranked compatibility · {stop.data_confidence || 'available data'} confidence</Text>
    {added ? <View accessibilityRole="text" accessibilityLabel="Stop added to route" style={styles.added}><Text style={styles.addedText}>✓ Stop Added to Route</Text></View> : onAddStop ? <Pressable accessibilityRole="button" accessibilityState={{ disabled: busy }} disabled={busy} style={[styles.action, busy && styles.disabled]} onPress={onAddStop}>{busy ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.actionText}>{actionLabel}</Text>}</Pressable> : null}
  </View>;
}
function InfoPill({ text, success = false }: { text: string; success?: boolean }) {
  if (!success) return <View style={styles.infoPill}><Text style={styles.infoText}>{text}</Text></View>;
  return <View style={[styles.infoPill, styles.successPill]}><MetricValueText value={text} numberStyle={styles.successNumber} unitStyle={styles.successUnit} /></View>;
}
function Evidence({ label, value }: { label: string; value: string }) { return <View style={styles.evidenceItem}><Text style={styles.evidenceLabel}>{label}</Text><MetricValueText value={value} numberStyle={styles.evidenceNumber} unitStyle={styles.evidenceUnit} /></View>; }

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderColor: routeColors.border, borderRadius: routeRadius.md, padding: routeSpacing.md, marginTop: routeSpacing.md }, header: { flexDirection: 'row', gap: routeSpacing.sm }, copy: { flex: 1 }, name: { color: routeColors.textPrimary, fontWeight: '800', fontSize: 14 }, address: { color: routeColors.textSecondary, fontSize: 10, marginTop: 4 },
  distancePill: { backgroundColor: routeColors.brandSoft, borderRadius: routeRadius.pill, paddingHorizontal: 10, height: 28, justifyContent: 'center' }, distanceNumber: { color: routeColors.brand, fontWeight: '900', fontSize: 13, fontVariant: ['tabular-nums'] }, distanceUnit: { color: routeColors.brand, fontWeight: '700', fontSize: 10 },
  pills: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: routeSpacing.sm }, infoPill: { borderWidth: 1, borderColor: routeColors.border, borderRadius: routeRadius.pill, paddingHorizontal: 9, paddingVertical: 5 }, infoText: { color: routeColors.textPrimary, fontWeight: '700', fontSize: 9 },
  successPill: { backgroundColor: routeColors.successSoft, borderColor: routeColors.successSoft }, successNumber: { color: routeColors.success, fontWeight: '900', fontSize: 12, fontVariant: ['tabular-nums'] }, successUnit: { color: routeColors.success, fontWeight: '700', fontSize: 9 },
  evidence: { flexDirection: 'row', flexWrap: 'wrap', gap: routeSpacing.sm, marginTop: routeSpacing.md }, evidenceItem: { width: '31%' }, evidenceLabel: { color: routeColors.textSecondary, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8 }, evidenceNumber: { color: routeColors.textPrimary, fontSize: 18, fontWeight: '900', fontVariant: ['tabular-nums'], marginTop: 2 }, evidenceUnit: { color: routeColors.textSecondary, fontSize: 10, fontWeight: '700' }, rank: { color: routeColors.brand, fontSize: 9, marginTop: routeSpacing.sm },
  action: { minHeight: 46, borderRadius: routeRadius.md, backgroundColor: routeColors.brand, alignItems: 'center', justifyContent: 'center', marginTop: routeSpacing.md }, disabled: { opacity: 0.55 }, actionText: { color: '#FFFFFF', fontWeight: '800', fontSize: 13 }, added: { minHeight: 44, borderRadius: routeRadius.md, backgroundColor: routeColors.successSoft, alignItems: 'center', justifyContent: 'center', marginTop: routeSpacing.md }, addedText: { color: routeColors.success, fontWeight: '800' },
});
