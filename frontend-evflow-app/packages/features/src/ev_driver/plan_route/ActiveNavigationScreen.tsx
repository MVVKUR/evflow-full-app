import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { LeafletMap } from '@evflow/ui';
import {
  createRoutePlan,
  evaluateActiveRoute,
  RouteApiError,
  type ActiveRouteEvaluationResponse,
  type ManualVehicleInput,
  type RecommendedStop,
  type RoutePlanResponse,
  type RoutePreferencesInput,
} from '@evflow/shared';
import { watchNavigationLocation, type NavigationFix } from '../utils/location';
import { NavigationWatcherSession } from './navigationSession';
import { buildRouteRequest, formatRouteEta, nonIncreasingDrivingSoc, suitableActiveStops } from './routePlanningLogic';
import {
  advanceStep,
  distanceMeters,
  isOffRoute,
  maneuverDistances,
  matchRoute,
  monotonicDistance,
  nextManeuverDistanceM,
  type RouteMatch,
} from './navigationProgress';
import { formatDistance, formatDuration, formatSoc } from './planRouteUtils';
import { getReserveCopy } from './reserveCopy';
import type { LocationState } from './planRouteTypes';
import { RouteDialog } from './components/RouteDialog';
import { routeColors } from './routeTheme';
import { buildNavigationMarkers } from './navigationMarkers';

export type NavigationSnapshot = {
  result: RoutePlanResponse;
  cumulativeDistanceKm: number;
  estimatedCurrentSocPct: number;
  routeBaseDistanceKm: number;
};

type Props = {
  result: RoutePlanResponse;
  destination: LocationState;
  navigationStartSocPct: number;
  initialCumulativeDistanceKm?: number;
  initialRouteBaseDistanceKm?: number;
  initialEstimatedCurrentSocPct?: number;
  manualVehicle?: ManualVehicleInput;
  evModelId?: string;
  preferences: Required<RoutePreferencesInput>;
  minimumArrivalSocPct: number;
  onOverview: (snapshot: NavigationSnapshot) => void;
  onEndNavigation: () => void | Promise<void>;
  onCancel: () => void | Promise<void>;
  onCompleted: () => void | Promise<void>;
  onRouteReplaced: (result: RoutePlanResponse) => void;
  onRouteSessionReplaced: (oldRoutePlanId: string) => void | Promise<void>;
  onConnectionError?: () => void;
  onConnectionRestored?: () => void;
  bottomOffset?: number;
  destinationName?: string;
  topInset?: number;
};

function maneuverIcon(instruction = '') {
  const text = instruction.toLowerCase();
  if (text.includes('u-turn')) return '↩';
  if (text.includes('roundabout')) return '↻';
  if (text.includes('left')) return '←';
  if (text.includes('right')) return '→';
  if (text.includes('arrive')) return '●';
  return '↑';
}

function connectorLabel(stop: RecommendedStop): string {
  return stop.matched_connector_type
    || stop.station.connector_types?.map((connector) => typeof connector === 'string' ? connector : connector.type).filter(Boolean)[0]
    || 'Connector details unavailable';
}

export function ActiveNavigationScreen({
  result,
  destination,
  navigationStartSocPct,
  initialCumulativeDistanceKm = 0,
  initialRouteBaseDistanceKm = 0,
  initialEstimatedCurrentSocPct,
  manualVehicle,
  evModelId,
  preferences,
  minimumArrivalSocPct,
  onOverview,
  onEndNavigation,
  onCancel,
  onCompleted,
  onRouteReplaced,
  onRouteSessionReplaced,
  bottomOffset = 0,
  destinationName = 'Destination',
  topInset = 0,
  onConnectionError,
  onConnectionRestored,
}: Props) {
  const [routeResult, setRouteResult] = useState(result);
  const [fix, setFix] = useState<NavigationFix | null>(null);
  const [routeMatch, setRouteMatch] = useState<RouteMatch | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [evaluation, setEvaluation] = useState<ActiveRouteEvaluationResponse | null>(null);
  const [status, setStatus] = useState<'navigating' | 'rerouting' | 'routing_unavailable'>('navigating');
  const [gpsUnavailable, setGpsUnavailable] = useState(false);
  const [ending, setEnding] = useState(false);
  const [addingStopId, setAddingStopId] = useState<string | null>(null);
  const [confirmEnd, setConfirmEnd] = useState(false);

  const routeRef = useRef(routeResult);
  const lineRef = useRef(routeResult.route.geometry.coordinates || []);
  const stepsRef = useRef(routeResult.route.steps || []);
  const maneuversRef = useRef(maneuverDistances(stepsRef.current, lineRef.current));
  const stepIndexRef = useRef(0);
  const latestFixRef = useRef<NavigationFix | null>(null);
  const latestEvaluationAtRef = useRef(0);
  const latestEvaluationLocationRef = useRef<NavigationFix | null>(null);
  const evaluationRef = useRef<ActiveRouteEvaluationResponse | null>(null);
  const cumulativeDistanceRef = useRef(initialCumulativeDistanceKm);
  const routeBaseDistanceRef = useRef(initialRouteBaseDistanceKm);
  const estimatedCurrentSocRef = useRef(initialEstimatedCurrentSocPct ?? navigationStartSocPct);
  const invalidFixesRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const requestSequenceRef = useRef(0);
  const watcherRef = useRef(new NavigationWatcherSession<NavigationFix>(watchNavigationLocation));
  const stoppedRef = useRef(false);
  const reroutingRef = useRef(false);
  const completingRef = useRef(false);

  const updateRoute = useCallback((next: RoutePlanResponse) => {
    routeRef.current = next;
    lineRef.current = next.route.geometry.coordinates || [];
    stepsRef.current = next.route.steps || [];
    maneuversRef.current = maneuverDistances(stepsRef.current, lineRef.current);
    stepIndexRef.current = 0;
    routeBaseDistanceRef.current = cumulativeDistanceRef.current;
    setRouteResult(next);
    setStepIndex(0);
    setRouteMatch(null);
    setEvaluation(null);
    evaluationRef.current = null;
    onRouteReplaced(next);
  }, [onRouteReplaced]);

  const stopTracking = useCallback(() => {
    if (stoppedRef.current) return;
    stoppedRef.current = true;
    watcherRef.current.stop();
    abortRef.current?.abort();
    latestFixRef.current = null;
    setFix(null);
    setRouteMatch(null);
  }, []);

  const replaceRoadRoute = useCallback(async (position: NavigationFix, stationId?: string) => {
    if (reroutingRef.current || stoppedRef.current) return;
    reroutingRef.current = true;
    setStatus('rerouting');
    abortRef.current?.abort();
    const oldRouteId = routeRef.current.route_plan_id;
    try {
      const replacement = await createRoutePlan(buildRouteRequest({
        origin: { latitude: position.latitude, longitude: position.longitude, label: 'Current location' },
        destination,
        currentSocPct: estimatedCurrentSocRef.current,
        minimumArrivalSocPct,
        preferences,
        manualVehicle,
        evModelId,
        waypointStationId: stationId || routeRef.current.user_requested_stop?.station.id || undefined,
      }));
      if (!stoppedRef.current) {
        updateRoute(replacement);
        invalidFixesRef.current = 0;
        setStatus('navigating');
        onConnectionRestored?.();
        void onRouteSessionReplaced(oldRouteId);
      }
    } catch (cause) {
      if (!stoppedRef.current) {
        setStatus('routing_unavailable');
        if ((cause as RouteApiError).isNetworkError) onConnectionError?.();
      }
    } finally {
      reroutingRef.current = false;
    }
  }, [destination, evModelId, manualVehicle, minimumArrivalSocPct, onConnectionError, onConnectionRestored, onRouteSessionReplaced, preferences, updateRoute]);

  const requestEvaluation = useCallback(async (position: NavigationFix, force = false) => {
    if (stoppedRef.current) return;
    const moved = latestEvaluationLocationRef.current
      ? distanceMeters(position, latestEvaluationLocationRef.current)
      : Infinity;
    if (!force && Date.now() - latestEvaluationAtRef.current < 8000 && moved < 200) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const sequence = ++requestSequenceRef.current;
    try {
      const value = await evaluateActiveRoute({
        route_plan_id: routeRef.current.route_plan_id,
        current_position: position,
        destination,
        navigation_start_soc_pct: navigationStartSocPct,
        cumulative_distance_travelled_km: cumulativeDistanceRef.current,
        minimum_arrival_soc_pct: minimumArrivalSocPct,
        maximum_detour_km: preferences.maximum_detour_km,
        active_waypoint_station_id: routeRef.current.user_requested_stop?.station.id,
        vehicle: manualVehicle,
        ev_model_id: evModelId,
      }, controller.signal);
      if (!stoppedRef.current && sequence === requestSequenceRef.current) {
        estimatedCurrentSocRef.current = nonIncreasingDrivingSoc(
          estimatedCurrentSocRef.current,
          value.estimated_current_soc_pct,
        );
        evaluationRef.current = { ...value, estimated_current_soc_pct: estimatedCurrentSocRef.current };
        setEvaluation(evaluationRef.current);
        latestEvaluationAtRef.current = Date.now();
        latestEvaluationLocationRef.current = position;
        onConnectionRestored?.();
      }
    } catch (cause: any) {
      if (cause?.name !== 'AbortError' && !stoppedRef.current) {
        setStatus('routing_unavailable');
        if ((cause as RouteApiError).isNetworkError) onConnectionError?.();
      }
    }
  }, [destination, evModelId, manualVehicle, minimumArrivalSocPct, navigationStartSocPct, onConnectionError, onConnectionRestored, preferences.maximum_detour_km]);

  const processFixRef = useRef<(position: NavigationFix) => void>(() => undefined);
  processFixRef.current = (position) => {
    if (stoppedRef.current) return;
    latestFixRef.current = position;
    setFix(position);
    setGpsUnavailable(false);
    const line = lineRef.current;
    if (line.length < 2) {
      setStatus('routing_unavailable');
      return;
    }
    const matched = matchRoute(position, line);
    setRouteMatch(matched);
    const cumulativeKm = routeBaseDistanceRef.current + matched.travelledM / 1000;
    cumulativeDistanceRef.current = monotonicDistance(cumulativeDistanceRef.current, cumulativeKm);
    const advanced = advanceStep(
      stepsRef.current,
      stepIndexRef.current,
      matched.point,
      matched.travelledM,
      maneuversRef.current,
    );
    if (advanced !== stepIndexRef.current) {
      stepIndexRef.current = advanced;
      setStepIndex(advanced);
    }
    invalidFixesRef.current = matched.distanceM > 50 ? invalidFixesRef.current + 1 : 0;
    if (isOffRoute(invalidFixesRef.current)) void replaceRoadRoute(position);
    void requestEvaluation(position, isOffRoute(invalidFixesRef.current));
    if (matched.remainingM <= 25 && !completingRef.current) {
      completingRef.current = true;
      stopTracking();
      void onCompleted();
    }
  };

  // One watcher for this mounted active-navigation session. Mutable route and
  // progress values are read through refs, so GPS fixes never restart it.
  useEffect(() => {
    stoppedRef.current = false;
    let disposed = false;
    void watcherRef.current.start(
      (position) => processFixRef.current(position),
      () => { if (!disposed) setGpsUnavailable(true); },
    );
    return () => {
      disposed = true;
      stopTracking();
    };
  }, [stopTracking]);

  const finish = useCallback(async (kind: 'end' | 'cancel') => {
    if (ending) return;
    setEnding(true);
    stopTracking();
    if (kind === 'cancel') await onCancel();
    else await onEndNavigation();
  }, [ending, onCancel, onEndNavigation, stopTracking]);

  const showOverview = useCallback(() => {
    stopTracking();
    onOverview({
      result: routeRef.current,
      cumulativeDistanceKm: cumulativeDistanceRef.current,
      estimatedCurrentSocPct: estimatedCurrentSocRef.current,
      routeBaseDistanceKm: routeBaseDistanceRef.current,
    });
  }, [onOverview, stopTracking]);

  const addStop = async (stop: RecommendedStop) => {
    if (!latestFixRef.current || addingStopId) return;
    setAddingStopId(stop.station.id);
    await replaceRoadRoute(latestFixRef.current, stop.station.id);
    setAddingStopId(null);
  };

  const line = routeResult.route.geometry.coordinates || [];
  const mapCenter = fix || (line[0]
    ? { latitude: line[0][1], longitude: line[0][0] }
    : { latitude: destination.latitude, longitude: destination.longitude });
  const currentStep = routeResult.route.steps?.[stepIndex];
  const nextStep = routeResult.route.steps?.[stepIndex + 1];
  const distanceToManeuverM = routeMatch
    ? nextManeuverDistanceM(stepIndex, routeMatch.travelledM, maneuversRef.current)
    : currentStep?.distance_m || 0;
  const remainingKm = evaluation?.remaining_distance_km
    ?? (routeMatch ? routeMatch.remainingM / 1000 : routeResult.summary.distance_km);
  const remainingMinutes = evaluation?.remaining_duration_minutes
    ?? (routeMatch ? routeResult.summary.duration_minutes * routeMatch.remainingM / Math.max(1, routeMatch.totalM) : routeResult.summary.duration_minutes);
  const projectedSoc = evaluation?.projected_arrival_soc_pct ?? routeResult.summary.estimated_arrival_soc_pct;
  const reserveCopy = getReserveCopy(projectedSoc, minimumArrivalSocPct);
  const currentSoc = evaluation?.estimated_current_soc_pct ?? navigationStartSocPct;
  const eta = evaluation?.estimated_arrival_at ?? routeResult.summary.estimated_arrival_at;
  const candidates = evaluation?.route_status === 'charging_required'
    ? suitableActiveStops(evaluation.candidate_stops)
    : [];

  return <View style={styles.container}>
    <View style={styles.mapWrap}><LeafletMap
      center={mapCenter}
      currentLocation={fix}
      showCurrentLocationPinpoint
      polylineCoordinates={line.map(([longitude, latitude]) => [latitude, longitude])}
      polylineColor={status === 'rerouting' ? '#EAB308' : '#00696F'}
      markers={buildNavigationMarkers(routeResult, destination, destinationName)}
    /></View>

    <View style={[styles.banner, { top: topInset + 12 }]}>
      {status === 'rerouting' ? <><Text style={styles.icon}>↻</Text><Text style={styles.instruction}>Rerouting</Text></>
        : <><Text style={styles.icon}>{maneuverIcon(nextStep?.instruction || currentStep?.instruction)}</Text><View style={styles.bannerCopy}><Text style={styles.distance}>{formatDistance(distanceToManeuverM / 1000)}</Text><Text style={styles.instruction}>{nextStep?.instruction || currentStep?.instruction || 'Continue to destination'}</Text>{(nextStep?.name || currentStep?.name) ? <Text style={styles.road}>{nextStep?.name || currentStep?.name}</Text> : null}</View></>}
    </View>

    {gpsUnavailable ? <View style={[styles.notice, { top: topInset + 104 }]}><Text style={styles.noticeTitle}>GPS unavailable</Text><Text>Enable precise location and move where the device has a clear signal.</Text></View> : null}
    {status === 'routing_unavailable' ? <View style={[styles.notice, { top: topInset + 104 }]}><Text style={styles.noticeTitle}>Road routing unavailable</Text><Text>Navigation will not use a straight-line substitute.</Text><View style={styles.noticeActions}><Pressable style={styles.secondaryAction} onPress={() => latestFixRef.current && replaceRoadRoute(latestFixRef.current)}><Text>Retry</Text></Pressable><Pressable style={styles.dangerAction} onPress={() => setConfirmEnd(true)}><Text style={styles.dangerText}>End navigation</Text></Pressable></View></View> : null}

    {evaluation?.warning ? <View style={[styles.warningPanel, { top: topInset + 104 }]}><View style={styles.warningHeading}><Text style={styles.noticeTitle}>{evaluation.warning.code === 'no_suitable_station' ? 'No suitable charging station' : 'Arrival battery recalculated'}</Text><Text style={styles.warningSoc}>{formatSoc(projectedSoc)}</Text></View><Text>{evaluation.warning.message}</Text>{evaluation.warning.code !== 'no_suitable_station' && reserveCopy ? <Text style={styles.reserveCopy}>{reserveCopy}</Text> : null}{candidates.length ? <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.stopList}>{candidates.map((stop) => <View style={styles.stopCard} key={stop.station.id}><Text style={styles.stopName}>{stop.station.name || 'Charging station'}</Text><Text>{formatDistance(stop.distance_from_origin_km)} away · {formatDistance(stop.detour_km)} detour</Text><Text>{connectorLabel(stop)} · {stop.best_available_power_kw ?? stop.station.power_kw ?? '—'} kW</Text><Text>{stop.available_connector_count} free · {Math.round(stop.estimated_charging_minutes)} min charge</Text><Pressable disabled={Boolean(addingStopId)} style={styles.addStop} onPress={() => void addStop(stop)}>{addingStopId === stop.station.id ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.addStopText}>Add SPKLU stop</Text>}</Pressable></View>)}</ScrollView> : <View style={styles.warningActions}><Pressable style={styles.secondaryAction} onPress={showOverview}><Text>Route overview</Text></Pressable><Pressable style={styles.dangerAction} onPress={() => setConfirmEnd(true)}><Text style={styles.dangerText}>End navigation</Text></Pressable></View>}</View> : null}

    <View style={[styles.sheet, { bottom: bottomOffset }]}>
      <View style={styles.stats}><Text style={styles.duration}>{formatDuration(remainingMinutes)}</Text><Text>{formatDistance(remainingKm)} left</Text><Text style={styles.soc}>{formatSoc(projectedSoc)} at arrival</Text></View>
      <Text style={styles.currentBattery}>Current battery {formatSoc(currentSoc)} · {formatRouteEta(eta)}</Text><Text style={styles.destination}>Destination · {destinationName}</Text>
      <View style={styles.actions}><Pressable accessibilityLabel="Show route overview" style={styles.secondaryAction} onPress={showOverview}><Text>Route overview</Text></Pressable><Pressable accessibilityLabel="End navigation" disabled={ending} style={styles.endAction} onPress={() => setConfirmEnd(true)}><Text style={styles.endText}>{ending ? 'Ending…' : 'End navigation'}</Text></Pressable></View>
    </View>
    <RouteDialog visible={confirmEnd} title="End navigation?" danger primaryLabel={ending ? 'Deleting session…' : 'End and delete session'} onPrimary={() => { setConfirmEnd(false); void finish('end'); }} secondaryLabel="Keep navigating" onSecondary={() => setConfirmEnd(false)}><Text>Route guidance stops immediately. Temporary route and battery data deletion starts now.</Text><View style={styles.privacyBox}><Text style={styles.privacyTitle}>Privacy process</Text><Text>1. Close route session</Text><Text>2. Mask coordinates in server logs</Text><Text>3. Delete temporary route data within 30 seconds</Text></View></RouteDialog>
  </View>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  mapWrap: { ...StyleSheet.absoluteFillObject },
  banner: { position: 'absolute', left: 12, right: 12, minHeight: 80, backgroundColor: '#00565F', borderRadius: 8, padding: 14, flexDirection: 'row', gap: 12, alignItems: 'center', zIndex: 20 },
  bannerCopy: { flex: 1 }, icon: { fontSize: 30, color: '#FFFFFF' }, distance: { color: '#CFFAFE', fontWeight: '700' }, instruction: { color: '#FFFFFF', fontSize: 17, fontWeight: '800' }, road: { color: '#E2E8F0' },
  notice: { position: 'absolute', left: 12, right: 12, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 8, padding: 14, zIndex: 22, gap: 6 },
  warningPanel: { position: 'absolute', left: 12, right: 12, maxHeight: 300, backgroundColor: '#FFF5EC', borderWidth: 1, borderColor: '#F2A261', borderRadius: 14, padding: 12, zIndex: 21, gap: 5 },
  warningHeading: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, warningSoc: { color: '#ED7100', fontWeight: '800' }, reserveCopy: { color: '#66747B', fontSize: 12 }, warningActions: { flexDirection: 'row', gap: 8, marginTop: 8 },
  noticeTitle: { color: '#0F172A', fontWeight: '800', fontSize: 16 }, noticeActions: { flexDirection: 'row', gap: 8, marginTop: 6 },
  stopList: { gap: 8, paddingTop: 8 }, stopCard: { width: 245, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 8, padding: 10, gap: 3 }, stopName: { fontWeight: '800', color: '#0F172A' }, addStop: { minHeight: 44, marginTop: 6, borderRadius: 6, backgroundColor: '#00696F', alignItems: 'center', justifyContent: 'center' }, addStopText: { color: '#FFFFFF', fontWeight: '800' },
  sheet: { position: 'absolute', left: 0, right: 0, backgroundColor: '#FFFFFF', padding: 18, borderTopLeftRadius: 24, borderTopRightRadius: 24, zIndex: 20 },
  stats: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }, duration: { fontSize: 20, fontWeight: '800' }, soc: { color: '#166534', fontWeight: '700' }, currentBattery: { color: '#475569', marginTop: 8 }, destination: { color: '#66747B', fontSize: 12, marginVertical: 8 }, actions: { flexDirection: 'row', gap: 8 }, secondaryAction: { minHeight: 48, flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 14, borderWidth: 1, borderColor: '#008A91', borderRadius: 12 }, dangerAction: { minHeight: 48, justifyContent: 'center', paddingHorizontal: 14, backgroundColor: '#B91C1C', borderRadius: 8 }, dangerText: { color: '#FFFFFF', fontWeight: '800' }, endAction: { minHeight: 48, flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#D5252A', borderRadius: 12 }, endText: { color: '#FFFFFF', fontWeight: '800' },
  privacyBox: { backgroundColor: routeColors.brandSoft, borderRadius: 12, padding: 12, gap: 5 }, privacyTitle: { color: routeColors.brandDark, fontWeight: '800', fontSize: 11, textTransform: 'uppercase' },
});
