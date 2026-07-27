import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { LeafletMap } from '@evflow/ui';
import { createRoutePlan, deleteRoutePlan, evaluateActiveRoute, type ActiveRouteEvaluationResponse, type RoutePlanResponse } from '@evflow/shared';
import { watchNavigationLocation, type NavigationFix } from '../utils/location';
import { advanceStep, distanceMeters, isOffRoute, matchRoute } from './navigationProgress';
import { formatDistance, formatDuration, formatSoc } from './planRouteUtils';
import type { LocationState } from './planRouteTypes';

type Props = { result: RoutePlanResponse; onOverview: () => void; onEndNavigation: () => void; bottomOffset?: number; destination?: LocationState | null; destinationName?: string; topInset?: number; minimumArrivalSocPct?: number; manualVehicleRangeKm?: number; };

const maneuverIcon = (instruction = '') => {
  const text = instruction.toLowerCase();
  if (text.includes('u-turn')) return '↩'; if (text.includes('roundabout')) return '↻';
  if (text.includes('left')) return '←'; if (text.includes('right')) return '→';
  if (text.includes('arrive')) return '●'; return '↑';
};

export function ActiveNavigationScreen({ result, onOverview, onEndNavigation, bottomOffset = 0, destination, destinationName = 'Destination', topInset = 0, minimumArrivalSocPct = 20, manualVehicleRangeKm }: Props) {
  const [routeResult, setRouteResult] = useState(result);
  const [fix, setFix] = useState<NavigationFix | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [evaluation, setEvaluation] = useState<ActiveRouteEvaluationResponse | null>(null);
  const [offRoute, setOffRoute] = useState(false);
  const [gpsUnavailable, setGpsUnavailable] = useState(false);
  const [ending, setEnding] = useState(false);
  const invalidFixes = useRef(0); const abort = useRef<AbortController | null>(null); const sequence = useRef(0); const lastEvaluation = useRef(0); const lastEvaluationPoint = useRef<NavigationFix | null>(null); const ended = useRef(false); const rerouting = useRef(false);
  const line = routeResult.route?.geometry?.coordinates || [];
  const match = useMemo(() => fix && line.length > 1 ? matchRoute(fix, line) : null, [fix, line]);
  const remainingKm = evaluation?.remaining_distance_km ?? (match ? match.remainingM / 1000 : routeResult.summary.distance_km);
  const remainingMinutes = evaluation?.remaining_duration_minutes ?? (match ? routeResult.summary.duration_minutes * (match.remainingM / Math.max(1, match.totalM)) : routeResult.summary.duration_minutes);
  const projectedSoc = evaluation?.projected_arrival_soc_pct ?? routeResult.summary.estimated_arrival_soc_pct;
  const currentStep = routeResult.route?.steps?.[stepIndex];

  const evaluate = useCallback(async (position: NavigationFix, force = false) => {
    if (ended.current || !destination) return;
    const moved = lastEvaluationPoint.current ? distanceMeters(position, lastEvaluationPoint.current) : Infinity;
    if (!force && Date.now() - lastEvaluation.current < 8000 && moved < 200) return;
    abort.current?.abort(); const controller = new AbortController(); abort.current = controller; const requestSequence = ++sequence.current;
    try {
      const value = await evaluateActiveRoute({ route_plan_id: routeResult.route_plan_id, current_position: position, destination, current_soc_pct: Math.min(result.summary.estimated_arrival_soc_pct + (match?.remainingM ?? 0) / Math.max(1, match?.totalM ?? 1) * (result.summary.minimum_arrival_soc_pct - result.summary.estimated_arrival_soc_pct), 100), minimum_arrival_soc_pct: minimumArrivalSocPct, maximum_detour_km: routeResult.assumptions.maximum_detour_km ?? 15, vehicle: manualVehicleRangeKm ? { usable_range_km: manualVehicleRangeKm } : undefined }, controller.signal);
      if (!ended.current && requestSequence === sequence.current) { setEvaluation(value); lastEvaluation.current = Date.now(); lastEvaluationPoint.current = position; }
    } catch (error: any) { if (error?.name !== 'AbortError') setGpsUnavailable(false); }
  }, [destination, manualVehicleRangeKm, match?.remainingM, match?.totalM, minimumArrivalSocPct, result.summary, routeResult.assumptions.maximum_detour_km, routeResult.route_plan_id]);

  const reroute = useCallback(async (position: NavigationFix) => {
    if (!destination || rerouting.current || ended.current) return;
    rerouting.current = true; setOffRoute(true); abort.current?.abort();
    try {
      const replacement = await createRoutePlan({ origin: { latitude: position.latitude, longitude: position.longitude, label: 'Current location' }, destination, current_soc_pct: Math.max(0, projectedSoc), minimum_arrival_soc_pct: minimumArrivalSocPct, preferences: { maximum_detour_km: routeResult.assumptions.maximum_detour_km ?? 15 }, waypoint_station_id: routeResult.user_requested_stop?.station.id ?? routeResult.recommended_stop?.station.id, vehicle: manualVehicleRangeKm ? { usable_range_km: manualVehicleRangeKm } : undefined });
      if (!ended.current) { const oldId = routeResult.route_plan_id; setRouteResult(replacement); setStepIndex(0); invalidFixes.current = 0; setOffRoute(false); void deleteRoutePlan(oldId); }
    } catch { /* Keep the explicit rerouting state; the driver can retry or end navigation. */ }
    finally { rerouting.current = false; }
  }, [destination, manualVehicleRangeKm, minimumArrivalSocPct, projectedSoc, routeResult.assumptions.maximum_detour_km, routeResult.recommended_stop?.station.id, routeResult.route_plan_id, routeResult.user_requested_stop?.station.id]);

  useEffect(() => {
    let subscription: { remove(): void } | null = null; let mounted = true;
    watchNavigationLocation((next) => {
      if (!mounted || ended.current) return; setFix(next); setGpsUnavailable(false);
      if (line.length > 1) { const mapped = matchRoute(next, line); invalidFixes.current = mapped.distanceM > 50 ? invalidFixes.current + 1 : 0; const nextIndex = advanceStep(routeResult.route.steps || [], stepIndex, mapped.point); if (nextIndex !== stepIndex) setStepIndex(nextIndex); if (isOffRoute(invalidFixes.current)) void reroute(next); }
      evaluate(next, isOffRoute(invalidFixes.current));
    }, () => mounted && setGpsUnavailable(true)).then((value) => { subscription = value; if (!value && mounted) setGpsUnavailable(true); });
    return () => { mounted = false; subscription?.remove(); abort.current?.abort(); };
  }, [evaluate, line, reroute, routeResult.route.steps, stepIndex]);

  const end = useCallback(async () => { if (ended.current) return; ended.current = true; setEnding(true); abort.current?.abort(); try { await deleteRoutePlan(routeResult.route_plan_id); } finally { setFix(null); setEvaluation(null); onEndNavigation(); } }, [onEndNavigation, routeResult.route_plan_id]);
  const retry = () => { if (fix) { setOffRoute(false); invalidFixes.current = 0; evaluate(fix, true); } };
  const center = fix || (line[0] ? { latitude: line[0][1], longitude: line[0][0] } : { latitude: -6.2088, longitude: 106.8456 });
  const distanceToTurn = currentStep?.location && match ? distanceMeters(match.point, { latitude: currentStep.location[1], longitude: currentStep.location[0] }) : currentStep?.distance_m || 0;

  return <View style={styles.container}>
    <View style={styles.mapWrap}><LeafletMap center={center} currentLocation={fix} showCurrentLocationPinpoint polylineCoordinates={line.map(([lon, lat]) => [lat, lon])} polylineColor={offRoute ? '#EAB308' : '#00696F'} markers={destination ? [{ id: 'destination', label: destinationName, latitude: destination.latitude, longitude: destination.longitude, type: 'destination' }] : []} /></View>
    <View style={[styles.banner, { top: topInset + 16 }]}>{offRoute ? <><Text style={styles.icon}>↻</Text><Text style={styles.instruction}>Rerouting</Text></> : currentStep ? <><Text style={styles.icon}>{maneuverIcon(currentStep.instruction)}</Text><View><Text style={styles.distance}>{formatDistance(distanceToTurn / 1000)}</Text><Text style={styles.instruction}>{currentStep.instruction || 'Continue'}</Text>{currentStep.name ? <Text style={styles.road}>{currentStep.name}</Text> : null}</View></> : <Text style={styles.instruction}>Continue to destination</Text>}</View>
    {gpsUnavailable ? <View style={styles.notice}><Text>GPS unavailable. Move to an area with a clear view of the sky, then retry.</Text><Pressable onPress={retry}><Text style={styles.link}>Retry</Text></Pressable></View> : null}
    {evaluation?.warning ? <View style={styles.notice}><Text>{evaluation.warning.message}</Text>{evaluation.candidate_stops[0] ? <Text style={styles.link}>Charging stop available: {evaluation.candidate_stops[0].station.name}</Text> : null}</View> : null}
    <View style={[styles.sheet, { bottom: bottomOffset }]}><View style={styles.stats}><Text style={styles.duration}>{formatDuration(remainingMinutes)}</Text><Text>{formatDistance(remainingKm)} left</Text><Text style={styles.soc}>{formatSoc(projectedSoc)} at arrival</Text></View><Text style={styles.eta}>{evaluation?.estimated_arrival_at ? `Arrives ${new Date(evaluation.estimated_arrival_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : `${destinationName}`}</Text><View style={styles.actions}><Pressable accessibilityLabel="Show route overview" style={styles.button} onPress={onOverview}><Text>Overview</Text></Pressable><Pressable accessibilityLabel="End navigation" disabled={ending} style={styles.end} onPress={end}><Text style={styles.endText}>{ending ? 'Ending...' : 'End Navigation'}</Text></Pressable></View></View>
  </View>;
}

const styles = StyleSheet.create({ container:{flex:1,backgroundColor:'#0F172A'},mapWrap:{...StyleSheet.absoluteFillObject},banner:{position:'absolute',left:16,right:16,backgroundColor:'#00565F',borderRadius:12,padding:14,flexDirection:'row',gap:12,alignItems:'center'},icon:{fontSize:28,color:'#fff'},distance:{color:'#CFFAFE',fontWeight:'700'},instruction:{color:'#fff',fontSize:17,fontWeight:'800'},road:{color:'#E2E8F0'},notice:{position:'absolute',left:16,right:16,top:120,backgroundColor:'#FFFBEB',padding:12,borderRadius:8,gap:4},link:{color:'#00696F',fontWeight:'700'},sheet:{position:'absolute',left:0,right:0,backgroundColor:'#fff',padding:20,borderTopLeftRadius:20,borderTopRightRadius:20},stats:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:8},duration:{fontSize:25,fontWeight:'800'},soc:{color:'#166534',fontWeight:'700'},eta:{color:'#475569',marginVertical:8},actions:{flexDirection:'row',gap:12},button:{minHeight:48,justifyContent:'center',paddingHorizontal:16},end:{minHeight:48,justifyContent:'center',paddingHorizontal:16,backgroundColor:'#00696F',borderRadius:8},endText:{color:'#fff',fontWeight:'800'} });
