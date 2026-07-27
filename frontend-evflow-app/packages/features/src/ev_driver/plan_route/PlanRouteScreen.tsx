import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import {
  createRoutePlan,
  deleteRoutePlan,
  type GeocodingItem,
  type ManualVehicleInput,
  type RoutePlanResponse,
  type RoutePreferencesInput,
} from '@evflow/shared';
import { DestinationSearchModal } from './DestinationSearchModal';
import { TripInputScreen } from './TripInputScreen';
import { TripSimulationScreen } from './TripSimulationScreen';
import { ActiveNavigationScreen, type NavigationSnapshot } from './ActiveNavigationScreen';
import { createRouteSessionCleaner } from './navigationSession';
import { buildRouteRequest, hasUsableVehicle } from './routePlanningLogic';
import { isImmersiveRouteView, transitionRouteView, type RouteViewAction } from './routeViewState';
import type { LocationState, RouteViewMode } from './planRouteTypes';

type PlanRouteScreenProps = {
  topInset?: number;
  bottomOffset?: number;
  onNavigationModeChange?: (active: boolean) => void;
};

const defaultPreferences: Required<RoutePreferencesInput> = {
  route_type: 'fastest',
  maximum_detour_km: 15,
  prefer_fast_charging: true,
};

export function PlanRouteScreen({ topInset = 0, bottomOffset = 0, onNavigationModeChange }: PlanRouteScreenProps) {
  const [viewMode, setViewMode] = useState<RouteViewMode>('input');
  const [origin, setOrigin] = useState<LocationState | null>(null);
  const [destination, setDestination] = useState<LocationState | null>(null);
  const [currentSocPct, setCurrentSocPct] = useState(72);
  const [socInputText, setSocInputText] = useState('72');
  const [minimumArrivalSocPct, setMinimumArrivalSocPct] = useState(20);
  const [preferences, setPreferences] = useState<Required<RoutePreferencesInput>>(defaultPreferences);
  const [manualVehicle, setManualVehicle] = useState<ManualVehicleInput>({ usable_range_km: 0 });
  const [hasVehicleProfile, setHasVehicleProfile] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [simulationResult, setSimulationResult] = useState<RoutePlanResponse | null>(null);
  const [searchModalVisible, setSearchModalVisible] = useState(false);
  const [navigationStartSocPct, setNavigationStartSocPct] = useState(currentSocPct);
  const [navigationEstimatedCurrentSocPct, setNavigationEstimatedCurrentSocPct] = useState(currentSocPct);
  const [cumulativeDistanceKm, setCumulativeDistanceKm] = useState(0);
  const [routeBaseDistanceKm, setRouteBaseDistanceKm] = useState(0);
  const sessionRef = useRef<RoutePlanResponse | null>(null);
  const modeRef = useRef<RouteViewMode>('input');
  const sessionCleanerRef = useRef(createRouteSessionCleaner(deleteRoutePlan));
  const planningAbort = useRef<AbortController | null>(null);

  useEffect(() => { sessionRef.current = simulationResult; }, [simulationResult]);
  useEffect(() => { modeRef.current = viewMode; }, [viewMode]);

  const cleanupRouteSession = useCallback(async (routePlanId?: string) => {
    const id = routePlanId ?? sessionRef.current?.route_plan_id;
    planningAbort.current?.abort();
    try { await sessionCleanerRef.current(id); } catch { /* Server TTL remains the privacy fallback. */ }
  }, []);

  const changeView = useCallback((action: RouteViewAction) => {
    setViewMode((current) => transitionRouteView(current, action));
  }, []);

  useEffect(() => {
    onNavigationModeChange?.(isImmersiveRouteView(viewMode));
  }, [onNavigationModeChange, viewMode]);

  useEffect(() => () => {
    onNavigationModeChange?.(false);
    void cleanupRouteSession();
  }, [cleanupRouteSession, onNavigationModeChange]);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => {
      if (state !== 'active' && modeRef.current === 'active_navigation') {
        void cleanupRouteSession();
        setSimulationResult(null);
        setViewMode('input');
      }
    });
    return () => subscription.remove();
  }, [cleanupRouteSession]);

  function handleSocTextChange(text: string) {
    setSocInputText(text);
    const value = Number(text.replace(/[^0-9.]/g, ''));
    if (Number.isFinite(value) && value >= 0 && value <= 100) setCurrentSocPct(value);
  }

  function handleQuickSelectSoc(value: number) {
    setCurrentSocPct(value);
    setSocInputText(String(value));
  }

  function handleSelectDestination(item: GeocodingItem) {
    const station = item.type === 'station' ? item.station : null;
    setDestination({
      latitude: station?.latitude ?? item.latitude,
      longitude: station?.longitude ?? item.longitude,
      label: station?.name || item.label,
    });
    setSearchModalVisible(false);
  }

  const requestVehicle = !hasVehicleProfile && hasUsableVehicle(false, manualVehicle)
    ? manualVehicle
    : undefined;

  async function handleSimulateRoute(waypointStationId?: string): Promise<RoutePlanResponse> {
    if (!origin || !destination) throw new Error('Choose an origin and destination first');
    if (!hasVehicleProfile && !requestVehicle) throw new Error('Enter a valid usable vehicle range');
    planningAbort.current?.abort();
    const controller = new AbortController();
    planningAbort.current = controller;
    setIsSimulating(true);
    setError(null);
    try {
      const result = await createRoutePlan(buildRouteRequest({
        origin, destination, currentSocPct, minimumArrivalSocPct, preferences,
        manualVehicle: requestVehicle, waypointStationId,
      }), controller.signal);
      const replacedId = sessionRef.current?.route_plan_id;
      setSimulationResult(result);
      setCumulativeDistanceKm(0);
      setRouteBaseDistanceKm(0);
      sessionRef.current = result;
      if (replacedId && replacedId !== result.route_plan_id) void cleanupRouteSession(replacedId);
      changeView('simulate');
      return result;
    } catch (cause: any) {
      if (cause?.name !== 'AbortError') setError(cause?.message || 'Failed to simulate route');
      throw cause;
    } finally {
      if (planningAbort.current === controller) setIsSimulating(false);
    }
  }

  async function cancelRoute() {
    await cleanupRouteSession();
    setSimulationResult(null);
    setCumulativeDistanceKm(0);
    setRouteBaseDistanceKm(0);
    setNavigationEstimatedCurrentSocPct(currentSocPct);
    changeView('cancel');
  }

  async function finishRoute(action: 'end_navigation' | 'complete') {
    await cleanupRouteSession();
    setSimulationResult(null);
    setCumulativeDistanceKm(0);
    setRouteBaseDistanceKm(0);
    setNavigationEstimatedCurrentSocPct(currentSocPct);
    changeView(action);
  }

  function startNavigation() {
    if (cumulativeDistanceKm === 0) {
      setNavigationStartSocPct(currentSocPct);
      setNavigationEstimatedCurrentSocPct(currentSocPct);
    }
    changeView('start_navigation');
  }

  function showOverview(snapshot: NavigationSnapshot) {
    setSimulationResult(snapshot.result);
    sessionRef.current = snapshot.result;
    setCumulativeDistanceKm(snapshot.cumulativeDistanceKm);
    setRouteBaseDistanceKm(snapshot.routeBaseDistanceKm);
    setNavigationEstimatedCurrentSocPct(snapshot.estimatedCurrentSocPct);
    changeView('overview');
  }

  if (viewMode === 'active_navigation' && simulationResult && destination) {
    return <ActiveNavigationScreen
      result={simulationResult}
      destination={destination}
      destinationName={destination.label || 'Destination'}
      topInset={topInset}
      bottomOffset={0}
      navigationStartSocPct={navigationStartSocPct}
      initialCumulativeDistanceKm={cumulativeDistanceKm}
      initialRouteBaseDistanceKm={routeBaseDistanceKm}
      initialEstimatedCurrentSocPct={navigationEstimatedCurrentSocPct}
      manualVehicle={requestVehicle}
      minimumArrivalSocPct={minimumArrivalSocPct}
      preferences={preferences}
      onOverview={showOverview}
      onCancel={() => finishRoute('end_navigation')}
      onCompleted={() => finishRoute('complete')}
      onEndNavigation={() => finishRoute('end_navigation')}
      onRouteReplaced={(result) => { setSimulationResult(result); sessionRef.current = result; }}
      onRouteSessionReplaced={cleanupRouteSession}
    />;
  }

  if (viewMode === 'completed') {
    return <View style={[styles.completed, { paddingTop: topInset, paddingBottom: bottomOffset }]}>
      <Text style={styles.completedTitle}>Destination reached</Text>
      <Text style={styles.completedText}>Navigation and temporary route data have been cleared.</Text>
      <Pressable style={styles.completedButton} onPress={() => changeView('cancel')}><Text style={styles.completedButtonText}>Plan another trip</Text></Pressable>
    </View>;
  }

  return <View style={[styles.shell, { paddingTop: topInset, paddingBottom: bottomOffset }]}>
    {viewMode === 'simulation' && simulationResult ? <TripSimulationScreen
      result={simulationResult}
      origin={origin}
      destination={destination}
      originLabel={origin?.label.split('—')[0].trim() || 'Origin'}
      destinationLabel={destination?.label || 'Destination'}
      preferences={preferences}
      minimumArrivalSocPct={minimumArrivalSocPct}
      isRecalculating={isSimulating}
      onEditTrip={cancelRoute}
      onCancel={cancelRoute}
      onAdjustPreferences={cancelRoute}
      onChooseAnotherRoute={async () => {
        setPreferences((value) => ({ ...value, route_type: value.route_type === 'fastest' ? 'shortest' : 'fastest' }));
        await cancelRoute();
      }}
      onChargeBeforeDeparture={cancelRoute}
      onStartNavigation={startNavigation}
      onAddStopToRoute={handleSimulateRoute}
    /> : <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
      <TripInputScreen
        origin={origin}
        destination={destination}
        currentSocPct={currentSocPct}
        socInputText={socInputText}
        manualVehicle={manualVehicle}
        minimumArrivalSocPct={minimumArrivalSocPct}
        preferences={preferences}
        onSetOrigin={setOrigin}
        onOpenDestinationSearch={() => setSearchModalVisible(true)}
        onChangeSocText={handleSocTextChange}
        onQuickSelectSoc={handleQuickSelectSoc}
        onManualVehicleChange={setManualVehicle}
        onMinimumArrivalSocChange={setMinimumArrivalSocPct}
        onPreferencesChange={setPreferences}
        onVehicleProfileAvailable={setHasVehicleProfile}
        onSimulate={() => { void handleSimulateRoute(); }}
        isSimulating={isSimulating}
        error={error}
      />
    </ScrollView>}
    <DestinationSearchModal visible={searchModalVisible} onClose={() => setSearchModalVisible(false)} onSelect={handleSelectDestination} originLat={origin?.latitude} originLon={origin?.longitude} />
  </View>;
}

const styles = StyleSheet.create({
  shell: { flex: 1, backgroundColor: '#F8FAFC' },
  scroll: { flex: 1 },
  scrollContent: { flexGrow: 1 },
  completed: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, backgroundColor: '#F8FAFC' },
  completedTitle: { fontSize: 28, fontWeight: '800', color: '#0F172A' },
  completedText: { marginTop: 8, color: '#475569', textAlign: 'center' },
  completedButton: { marginTop: 24, minHeight: 48, paddingHorizontal: 20, justifyContent: 'center', backgroundColor: '#00696F', borderRadius: 8 },
  completedButtonText: { color: '#FFFFFF', fontWeight: '800' },
});
