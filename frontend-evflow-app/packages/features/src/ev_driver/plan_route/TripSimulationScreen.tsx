import { useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { RecommendedStop, RoutePlanResponse, RoutePreferencesInput } from '@evflow/shared';
import { ChargingStopCard } from './ChargingStopCard';
import { RouteBottomSheet } from './components/RouteBottomSheet';
import { RouteMetricsGrid } from './components/RouteMetricsGrid';
import { RouteStatusCard } from './components/RouteStatusCard';
import { canStartNavigation, noSuitableStationReasons, routePresentation } from './routePlanningLogic';
import { formatDistance, formatDuration, formatEnergy, formatSoc } from './planRouteUtils';
import { routeColors, routeRadius, routeSpacing } from './routeTheme';

type Props = {
  result: RoutePlanResponse; expanded: boolean; onToggleExpanded: () => void; bottomOffset?: number; topInset?: number;
  onEditTrip: () => void; onCancel: () => void | Promise<void>; onChooseAnotherRoute: () => void | Promise<void>; onAdjustPreferences: () => void | Promise<void>; onChargeBeforeDeparture: () => void | Promise<void>; onStartNavigation: () => void;
  onAddStopToRoute: (stationId: string) => Promise<RoutePlanResponse>; originLabel?: string; destinationLabel?: string; preferences: Required<RoutePreferencesInput>; minimumArrivalSocPct: number; isRecalculating?: boolean;
};

export function TripSimulationScreen({ result, expanded, onToggleExpanded, bottomOffset = 0, topInset = 0, onCancel, onChooseAnotherRoute, onAdjustPreferences, onChargeBeforeDeparture, onStartNavigation, onAddStopToRoute, originLabel = 'Origin', destinationLabel = 'Destination', preferences, minimumArrivalSocPct, isRecalculating = false }: Props) {
  const [addingId, setAddingId] = useState<string | null>(null);
  const [showAlternatives, setShowAlternatives] = useState(false);
  const presentation = routePresentation(result);
  const direct = presentation === 'direct';
  const noStation = presentation === 'no_suitable_station';
  const addedStop = result.user_requested_stop ?? null;
  const recommendation = addedStop ?? result.recommended_stop ?? null;
  const safeToStart = canStartNavigation(result);
  const preferenceLabel = preferences.route_type === 'shortest' ? 'Least detour' : preferences.prefer_fast_charging ? 'Fastest' : 'Available now';

  async function add(stop: RecommendedStop) {
    if (addingId || isRecalculating) return;
    setAddingId(stop.station.id);
    try { await onAddStopToRoute(stop.station.id); setShowAlternatives(false); }
    finally { setAddingId(null); }
  }

  async function handleStartNavigation() {
    if (addingId || isRecalculating) return;
    if (safeToStart) {
      onStartNavigation();
    } else if (recommendation) {
      setAddingId(recommendation.station.id);
      try {
        await onAddStopToRoute(recommendation.station.id);
        setShowAlternatives(false);
        onStartNavigation();
      } finally {
        setAddingId(null);
      }
    }
  }

  const isStartDisabled = Boolean(addingId) || isRecalculating || (!safeToStart && !recommendation);

  const metrics = [
    { label: 'Total distance', value: formatDistance(result.summary.distance_km) },
    { label: 'Energy use', value: formatEnergy(result.summary.estimated_energy_kwh) },
    { label: 'Arrival battery', value: formatSoc(result.summary.estimated_arrival_soc_pct), tone: direct || addedStop ? 'success' as const : 'warning' as const },
    { label: addedStop ? 'Total duration' : 'Est. duration', value: formatDuration(result.summary.duration_minutes) },
  ];

  return <>
    <RouteBottomSheet bottom={bottomOffset} scroll={expanded} top={expanded ? topInset + 88 : undefined}>
      <Pressable accessibilityRole="button" accessibilityLabel={expanded ? 'Collapse route details' : 'Expand route details'} onPress={onToggleExpanded}>
        {addedStop ? <RouteStatusCard tone="success" title="Charging stop added" message={`Charge to ${Math.round(addedStop.recommended_target_soc_pct)}% for about ${Math.round(addedStop.estimated_charging_minutes)} minutes.`} />
          : noStation ? <RouteStatusCard tone="error" title="No suitable charging station" message={result.warning?.message || 'No compatible, available station is reachable with the requested reserve.'} />
          : direct ? <RouteStatusCard tone="success" title="Direct route available" message={`You arrive above the ${minimumArrivalSocPct}% safety reserve. No charging stop is needed.`} />
          : <RouteStatusCard tone="warning" title="Charging stop recommended" message={`Projected arrival is ${formatSoc(result.summary.estimated_arrival_soc_pct)}, below your ${minimumArrivalSocPct}% reserve.`} />}
      </Pressable>
      {expanded ? <>
        <View style={styles.spacer} /><RouteMetricsGrid metrics={metrics} />
        <View style={styles.preference}><Text style={styles.preferenceLabel}>Applied preference</Text><Text style={styles.preferenceValue}>{preferenceLabel} · {minimumArrivalSocPct}% reserve</Text></View>
        {addedStop ? <View style={styles.sequence}><Text style={styles.sequenceLabel}>Route plan</Text><Text style={styles.sequenceItem}>● {originLabel}</Text><Text style={styles.stopSequence}>⌁ {addedStop.station.name || 'Charging station'} · +{Math.round(addedStop.estimated_charging_minutes)} min</Text><Text style={styles.sequenceItem}>● {destinationLabel} · arrive {formatSoc(result.summary.estimated_arrival_soc_pct)}</Text></View> : null}
        {!direct && !noStation && recommendation ? <><Text style={styles.bestMatch}>Best match</Text><ChargingStopCard stop={recommendation} added={Boolean(addedStop)} busy={Boolean(addingId) || isRecalculating} onAddStop={addedStop ? undefined : () => void add(recommendation)} />{!addedStop && result.alternative_stops?.length ? <Pressable accessibilityRole="button" style={styles.alternatives} onPress={() => setShowAlternatives(true)}><Text style={styles.alternativesText}>View alternatives ({result.alternative_stops.length})</Text></Pressable> : null}</> : null}
        {noStation ? <View style={styles.reasons}><Text style={styles.reasonsTitle}>Why no station qualified</Text>{noSuitableStationReasons([...(result.alternative_stops || []), ...(result.recommended_stop ? [result.recommended_stop] : [])]).map((reason) => <Text key={reason} style={styles.reason}>• {reason}</Text>)}</View> : null}
        {noStation ? <><Action label="Choose another route" onPress={onChooseAnotherRoute} primary /><Action label="Adjust charging preferences" onPress={onAdjustPreferences} /><Action label="Charge before departure" onPress={onChargeBeforeDeparture} muted /></>
          : <Pressable accessibilityRole="button" accessibilityState={{ disabled: isStartDisabled }} disabled={isStartDisabled} style={[styles.start, isStartDisabled && styles.disabled]} onPress={() => void handleStartNavigation()}><Text style={styles.startText}>{addingId || isRecalculating ? 'Recalculating route…' : 'Start navigation'}</Text></Pressable>}
        <Pressable accessibilityRole="button" accessibilityLabel="Cancel route planning" style={styles.cancel} onPress={() => void onCancel()}><Text style={styles.cancelText}>Cancel</Text></Pressable>
      </> : null}
    </RouteBottomSheet>
    <Modal transparent animationType="slide" visible={showAlternatives} onRequestClose={() => setShowAlternatives(false)}><View style={styles.modalBackdrop}><View style={styles.modal}><View style={styles.modalHeader}><Text style={styles.modalTitle}>Alternative charging stops</Text><Pressable accessibilityLabel="Close alternatives" style={styles.close} onPress={() => setShowAlternatives(false)}><Text>×</Text></Pressable></View><ScrollView>{result.alternative_stops?.map((stop) => <ChargingStopCard key={stop.station.id} stop={stop} busy={Boolean(addingId)} actionLabel="Use this stop" onAddStop={() => void add(stop)} />)}</ScrollView></View></View></Modal>
  </>;
}

function Action({ label, onPress, primary = false, muted = false }: { label: string; onPress: () => void | Promise<void>; primary?: boolean; muted?: boolean }) { return <Pressable accessibilityRole="button" style={[styles.action, primary && styles.actionPrimary, muted && styles.actionMuted]} onPress={() => void onPress()}><Text style={[styles.actionText, primary && styles.actionPrimaryText]}>{label}</Text></Pressable>; }
const styles = StyleSheet.create({
  spacer: { height: routeSpacing.md }, preference: { marginTop: routeSpacing.md }, preferenceLabel: { color: routeColors.textSecondary, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }, preferenceValue: { color: routeColors.textPrimary, fontSize: 11, marginTop: 3 }, bestMatch: { color: routeColors.textSecondary, fontSize: 9, textTransform: 'uppercase', fontWeight: '700', marginTop: routeSpacing.md },
  sequence: { backgroundColor: routeColors.surfaceSecondary, borderRadius: routeRadius.md, padding: routeSpacing.md, marginTop: routeSpacing.md, gap: 6 }, sequenceLabel: { color: routeColors.textSecondary, fontSize: 9, textTransform: 'uppercase' }, sequenceItem: { color: routeColors.textPrimary, fontSize: 11 }, stopSequence: { color: routeColors.warning, fontSize: 11, fontWeight: '700' },
  reasons: { backgroundColor: routeColors.surfaceSecondary, borderRadius: routeRadius.md, padding: routeSpacing.md, marginTop: routeSpacing.md, gap: 7 }, reasonsTitle: { color: routeColors.textSecondary, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }, reason: { color: routeColors.textPrimary, fontSize: 11 },
  start: { minHeight: 52, borderRadius: routeRadius.md, backgroundColor: routeColors.brand, alignItems: 'center', justifyContent: 'center', marginTop: routeSpacing.md }, startText: { color: '#FFFFFF', fontWeight: '800' }, disabled: { backgroundColor: routeColors.disabled }, alternatives: { minHeight: 44, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: routeColors.brand, borderRadius: routeRadius.md, marginTop: routeSpacing.sm }, alternativesText: { color: routeColors.brand, fontWeight: '800' },
  cancel: { minHeight: 48, alignItems: 'center', justifyContent: 'center', marginTop: routeSpacing.sm }, cancelText: { color: routeColors.textPrimary, fontWeight: '800', fontSize: 13 },
  action: { minHeight: 50, borderWidth: 1.5, borderColor: routeColors.brand, borderRadius: routeRadius.md, alignItems: 'center', justifyContent: 'center', marginTop: routeSpacing.sm }, actionPrimary: { backgroundColor: routeColors.brand }, actionMuted: { backgroundColor: routeColors.surfaceSecondary, borderColor: routeColors.surfaceSecondary }, actionText: { color: routeColors.brand, fontWeight: '800' }, actionPrimaryText: { color: '#FFFFFF' },
  modalBackdrop: { flex: 1, backgroundColor: routeColors.overlay, justifyContent: 'flex-end' }, modal: { maxHeight: '78%', backgroundColor: routeColors.surface, borderTopLeftRadius: routeRadius.sheet, borderTopRightRadius: routeRadius.sheet, padding: routeSpacing.lg }, modalHeader: { flexDirection: 'row', alignItems: 'center' }, modalTitle: { flex: 1, fontWeight: '800', fontSize: 18, color: routeColors.textPrimary }, close: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
});
