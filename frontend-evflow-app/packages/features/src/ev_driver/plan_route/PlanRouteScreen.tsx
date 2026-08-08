import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Linking, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { LeafletMap, type LeafletMapMarker } from '@evflow/ui';
import {
  createRoutePlan,
  checkRouteApiHealth,
  deleteRoutePlan,
  reverseGeocode,
  RouteApiError,
  type GeocodingItem,
  type ManualVehicleInput,
  type RoutePlanResponse,
  type RoutePreferencesInput,
} from '@evflow/shared';
import { getUserLocation, type LocationPermissionStatus } from '../utils/location';
import { ActiveNavigationScreen, type NavigationSnapshot } from './ActiveNavigationScreen';
import { RouteBottomSheet } from './components/RouteBottomSheet';
import { RouteDialog } from './components/RouteDialog';
import { DestinationSearchModal, type LocationSearchMode } from './DestinationSearchModal';
import { createRouteSessionCleaner, shouldDeleteReplacedPlanningSession } from './navigationSession';
import { buildRouteRequest, clearFieldError, hasUsableVehicle, locationEntryDecision, validateRouteInput, type RouteInputErrors, type RouteInputField } from './routePlanningLogic';
import { isImmersiveRouteView, transitionPlannerSheet, transitionRouteView, type PlannerSheetMode, type RouteViewAction } from './routeViewState';
import { routeColors, routeRadius, routeShadow, routeSpacing } from './routeTheme';
import { TripInputScreen, type VehicleDisplay } from './TripInputScreen';
import { TripSimulationScreen } from './TripSimulationScreen';
import type { LocationState, PickedMapPoint, RouteViewMode } from './planRouteTypes';

type Props = { topInset?: number; bottomOffset?: number; onNavigationModeChange?: (active: boolean) => void };

const defaultPreferences: Required<RoutePreferencesInput> = { route_type: 'fastest', maximum_detour_km: 15, prefer_fast_charging: true };
const defaultCenter = { latitude: -6.1754, longitude: 106.8272 };

export function PlanRouteScreen({ topInset = 0, bottomOffset = 0, onNavigationModeChange }: Props) {
  const [viewMode, setViewMode] = useState<RouteViewMode>('input');
  const [sheetMode, setSheetMode] = useState<PlannerSheetMode>('peek');
  const [resultExpanded, setResultExpanded] = useState(true);
  const [plannerFocus, setPlannerFocus] = useState<'battery' | 'preferences' | null>(null);
  const [origin, setOrigin] = useState<LocationState | null>(null);
  const [destination, setDestination] = useState<LocationState | null>(null);
  const [currentSocPct, setCurrentSocPct] = useState(72);
  const [socInputText, setSocInputText] = useState('72');
  const [minimumArrivalSocPct, setMinimumArrivalSocPct] = useState(20);
  const [preferences, setPreferences] = useState<Required<RoutePreferencesInput>>(defaultPreferences);
  const [manualVehicle, setManualVehicle] = useState<ManualVehicleInput>({ usable_range_km: 0 });
  const [profileVehicle, setProfileVehicle] = useState<VehicleDisplay | null>(null);
  const [isSimulating, setIsSimulating] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<RouteInputErrors>({});
  const [simulationResult, setSimulationResult] = useState<RoutePlanResponse | null>(null);
  const [searchMode, setSearchMode] = useState<LocationSearchMode | null>(null);
  const [pickedPoint, setPickedPoint] = useState<PickedMapPoint | null>(null);
  const [locationDialog, setLocationDialog] = useState<LocationPermissionStatus | null>(null);
  const [connectionError, setConnectionError] = useState(false);
  const [navigationStartSocPct, setNavigationStartSocPct] = useState(currentSocPct);
  const [navigationEstimatedCurrentSocPct, setNavigationEstimatedCurrentSocPct] = useState(currentSocPct);
  const [cumulativeDistanceKm, setCumulativeDistanceKm] = useState(0);
  const [routeBaseDistanceKm, setRouteBaseDistanceKm] = useState(0);
  const sessionRef = useRef<RoutePlanResponse | null>(null);
  const modeRef = useRef<RouteViewMode>('input');
  const sessionCleanerRef = useRef(createRouteSessionCleaner(deleteRoutePlan));
  const planningAbort = useRef<AbortController | null>(null);
  const retryRef = useRef<(() => void) | null>(null);

  useEffect(() => { sessionRef.current = simulationResult; }, [simulationResult]);
  useEffect(() => { modeRef.current = viewMode; }, [viewMode]);
  // A tagged point belongs to one picking session: opening, switching, or
  // closing the search sheet always starts from a clean map.
  useEffect(() => { setPickedPoint(null); }, [searchMode]);
  const handleMapPick = useCallback((latitude: number, longitude: number) => setPickedPoint({ latitude, longitude }), []);

  const cleanupRouteSession = useCallback(async (routePlanId?: string) => {
    const id = routePlanId ?? sessionRef.current?.route_plan_id;
    planningAbort.current?.abort();
    try { await sessionCleanerRef.current(id); } catch { /* Server TTL is the privacy fallback. */ }
  }, []);

  const changeView = useCallback((action: RouteViewAction) => setViewMode((current) => transitionRouteView(current, action)), []);
  const blockingDialog = Boolean(locationDialog || connectionError);
  useEffect(() => { onNavigationModeChange?.(isImmersiveRouteView(viewMode) || blockingDialog); }, [blockingDialog, onNavigationModeChange, viewMode]);
  useEffect(() => () => { onNavigationModeChange?.(false); void cleanupRouteSession(); }, [cleanupRouteSession, onNavigationModeChange]);

  useEffect(() => {
    let mounted = true;
    void getUserLocation().then((result) => {
      if (!mounted) return;
      if (locationEntryDecision(result.status, Boolean(result.coordinates)) === 'use_location' && result.coordinates) void acceptCurrentLocation(result.coordinates.latitude, result.coordinates.longitude);
      else setLocationDialog(result.status);
    });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => {
      if (state !== 'active' && modeRef.current === 'active_navigation') {
        void cleanupRouteSession(); setSimulationResult(null); setViewMode('input'); setSheetMode('peek');
      }
    });
    return () => subscription.remove();
  }, [cleanupRouteSession]);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    const offline = () => setConnectionError(true);
    const online = () => { void checkRouteApiHealth().then(() => setConnectionError(false)).catch(() => setConnectionError(true)); };
    window.addEventListener('offline', offline); window.addEventListener('online', online);
    if (!window.navigator.onLine) offline();
    return () => { window.removeEventListener('offline', offline); window.removeEventListener('online', online); };
  }, []);

  async function acceptCurrentLocation(latitude: number, longitude: number) {
    setOrigin({ latitude, longitude, label: 'Current location' });
    setFieldErrors((value) => clearFieldError(value, 'origin'));
    try {
      const place = await reverseGeocode(latitude, longitude);
      setOrigin({ latitude, longitude, label: `Current location · ${place.label || place.city}` });
    } catch (cause) { if ((cause as RouteApiError).isNetworkError) setConnectionError(true); }
  }

  async function requestLocation() {
    const result = await getUserLocation({ requestPermission: true });
    if (result.coordinates) { setLocationDialog(null); await acceptCurrentLocation(result.coordinates.latitude, result.coordinates.longitude); }
    else setLocationDialog(result.status);
  }

  function updateField(field: RouteInputField, action: () => void) {
    action(); setFieldErrors((value) => clearFieldError(value, field)); setRouteError(null);
  }

  function changeSocText(text: string) {
    setSocInputText(text);
    const value = Number(text.replace(/[^0-9.]/g, ''));
    setCurrentSocPct(value);
    setFieldErrors((errors) => clearFieldError(errors, 'current_soc_pct')); setRouteError(null);
  }
  function selectSoc(value: number) { setCurrentSocPct(value); setSocInputText(String(value)); setFieldErrors((errors) => clearFieldError(errors, 'current_soc_pct')); }

  function selectLocation(item: GeocodingItem) {
    const station = item.type === 'station' ? item.station : null;
    const value = { latitude: station?.latitude ?? item.latitude, longitude: station?.longitude ?? item.longitude, label: station?.name || item.label };
    if (searchMode === 'origin') updateField('origin', () => setOrigin(value));
    else updateField('destination', () => setDestination(value));
    setSearchMode(null); setSheetMode('expanded');
  }

  const requestVehicle = !profileVehicle && hasUsableVehicle(false, manualVehicle) ? manualVehicle : undefined;
  const hasVehicle = Boolean(profileVehicle || requestVehicle);

  async function simulateRoute(waypointStationId?: string): Promise<RoutePlanResponse> {
    const localErrors = validateRouteInput({ origin, destination, currentSocPct, minimumArrivalSocPct, hasVehicle });
    if (Object.keys(localErrors).length) {
      setFieldErrors(localErrors); setRouteError('Choose valid route details before simulation.'); setSheetMode('expanded');
      throw new Error('Invalid route details');
    }
    planningAbort.current?.abort();
    const controller = new AbortController(); planningAbort.current = controller;
    setIsSimulating(true); setRouteError(null); retryRef.current = () => { void simulateRoute(waypointStationId).catch(() => undefined); };
    try {
      const result = await createRoutePlan(buildRouteRequest({ origin: origin!, destination: destination!, currentSocPct, minimumArrivalSocPct, preferences, manualVehicle: requestVehicle, evModelId: profileVehicle?.id, waypointStationId }), controller.signal);
      const replacedId = sessionRef.current?.route_plan_id;
      setSimulationResult(result); sessionRef.current = result; setCumulativeDistanceKm(0); setRouteBaseDistanceKm(0); setResultExpanded(true);
      if (shouldDeleteReplacedPlanningSession(replacedId, result.route_plan_id, waypointStationId)) {
        await cleanupRouteSession(replacedId);
      }
      changeView('simulate'); setConnectionError(false); return result;
    } catch (cause) {
      if ((cause as { name?: string })?.name === 'AbortError') throw cause;
      const error = cause as RouteApiError;
      if (error.isNetworkError) setConnectionError(true);
      else {
        setFieldErrors(error.fieldErrors || {}); setRouteError(error.message || 'Route simulation failed.'); setSheetMode(transitionPlannerSheet(sheetMode, 'invalid')); setViewMode('input');
      }
      throw cause;
    } finally { if (planningAbort.current === controller) setIsSimulating(false); }
  }

  async function cancelRoute(focus?: 'preferences' | 'battery') {
    await cleanupRouteSession(); setSimulationResult(null); sessionRef.current = null; setCumulativeDistanceKm(0); setRouteBaseDistanceKm(0); setNavigationEstimatedCurrentSocPct(currentSocPct); changeView('cancel'); setSheetMode(focus ? 'expanded' : 'peek');
    setPlannerFocus(focus ?? null);
    if (focus === 'battery') setRouteError('Increase the departure battery enough to preserve the requested reserve.');
  }
  async function finishRoute(action: 'end_navigation' | 'complete') {
    await cleanupRouteSession(); setSimulationResult(null); sessionRef.current = null; setCumulativeDistanceKm(0); setRouteBaseDistanceKm(0); setNavigationEstimatedCurrentSocPct(currentSocPct); setSheetMode('peek'); setViewMode(action === 'complete' ? 'completed' : 'input');
  }
  function startNavigation() { if (!cumulativeDistanceKm) { setNavigationStartSocPct(currentSocPct); setNavigationEstimatedCurrentSocPct(currentSocPct); } changeView('start_navigation'); }
  function showOverview(snapshot: NavigationSnapshot) { setSimulationResult(snapshot.result); sessionRef.current = snapshot.result; setCumulativeDistanceKm(snapshot.cumulativeDistanceKm); setRouteBaseDistanceKm(snapshot.routeBaseDistanceKm); setNavigationEstimatedCurrentSocPct(snapshot.estimatedCurrentSocPct); changeView('overview'); }

  if (viewMode === 'active_navigation' && simulationResult && destination) return <>
    <ActiveNavigationScreen result={simulationResult} destination={destination} destinationName={destination.label || 'Destination'} topInset={topInset} navigationStartSocPct={navigationStartSocPct} initialCumulativeDistanceKm={cumulativeDistanceKm} initialRouteBaseDistanceKm={routeBaseDistanceKm} initialEstimatedCurrentSocPct={navigationEstimatedCurrentSocPct} manualVehicle={requestVehicle} evModelId={profileVehicle?.id} minimumArrivalSocPct={minimumArrivalSocPct} preferences={preferences} onOverview={showOverview} onCancel={() => finishRoute('end_navigation')} onCompleted={() => finishRoute('complete')} onEndNavigation={() => finishRoute('end_navigation')} onRouteReplaced={(result) => { setSimulationResult(result); sessionRef.current = result; }} onRouteSessionReplaced={cleanupRouteSession} onConnectionError={() => setConnectionError(true)} onConnectionRestored={() => setConnectionError(false)} />
    <RouteDialog visible={connectionError} title="Lost connection" primaryLabel="Retry" onPrimary={() => { void checkRouteApiHealth().then(() => setConnectionError(false)).catch(() => setConnectionError(true)); }} secondaryLabel={Platform.OS === 'web' ? 'Close' : 'Connection settings'} onSecondary={() => Platform.OS === 'web' ? setConnectionError(false) : void Linking.openSettings()}><Text style={styles.dialogText}>Navigation is still open in memory. Reconnect to resume route evaluation.</Text></RouteDialog>
  </>;

  const line = simulationResult?.route.geometry.coordinates?.map(([longitude, latitude]) => [latitude, longitude] as [number, number]) ?? [];
  const markers: LeafletMapMarker[] = [];
  if (origin) markers.push({ id: 'origin', label: origin.label, latitude: origin.latitude, longitude: origin.longitude, type: 'origin' });
  if (destination) markers.push({ id: 'destination', label: destination.label, latitude: destination.latitude, longitude: destination.longitude, type: 'destination' });
  const stop = simulationResult?.user_requested_stop ?? simulationResult?.recommended_stop;
  if (stop) markers.push({ id: stop.station.id, label: stop.station.name ?? 'Charging stop', latitude: stop.station.latitude, longitude: stop.station.longitude, type: 'charging_stop' });
  const vehicleDisplay = profileVehicle ?? (manualVehicle.usable_range_km > 0 ? { name: manualVehicle.name || 'Manual EV', usableRangeKm: manualVehicle.usable_range_km, source: 'manual' as const } : null);

  return <View style={styles.shell}>
    <View style={StyleSheet.absoluteFill}><LeafletMap center={origin ?? defaultCenter} currentLocation={origin} showCurrentLocationPinpoint markers={markers} polylineCoordinates={line} polylineColor={simulationResult?.route_status === 'charging_required' ? routeColors.warning : simulationResult?.route_status === 'no_suitable_station' ? routeColors.error : routeColors.brand} autoFitBounds={line.length > 1} onMapPress={searchMode ? handleMapPick : undefined} onPickedPointMoved={searchMode ? handleMapPick : undefined} pickedPoint={searchMode ? pickedPoint : null} /></View>
    {viewMode === 'input' && sheetMode === 'peek' && !searchMode ? <Pressable accessibilityRole="button" accessibilityLabel="Open destination search" style={[styles.searchCard, { top: topInset + 18 }]} onPress={() => setSheetMode('expanded')}><Text style={styles.searchIcon}>⌕</Text><View><Text style={styles.searchLabel}>Plan a trip</Text><Text style={styles.searchText}>{destination?.label || 'Where are you going?'}</Text></View><Text style={styles.more}>⋮</Text></Pressable> : null}
    {viewMode === 'input' && sheetMode === 'peek' && !searchMode ? <View style={[styles.rangeBadge, { top: topInset + 92 }]}><Text style={styles.rangeText}>{Math.round(currentSocPct)}%{vehicleDisplay ? ` · ${Math.round(vehicleDisplay.usableRangeKm * currentSocPct / 100)} km range` : ''}</Text></View> : null}
    {viewMode === 'input' && sheetMode === 'peek' && !searchMode ? <View style={[styles.mapControls, { top: topInset + 118 }]}><Pressable accessibilityRole="button" accessibilityLabel="Recenter map on current location" style={styles.mapControl} onPress={() => void requestLocation()}><Text style={styles.mapControlText}>◎</Text></Pressable><View style={styles.controlDivider} /><Pressable accessibilityRole="button" accessibilityLabel="Choose origin" style={styles.mapControl} onPress={() => setSearchMode('origin')}><Text style={styles.mapControlText}>⌖</Text></Pressable></View> : null}
    {viewMode === 'simulation' && simulationResult ? <View style={[styles.routeHeader, { top: topInset + 18 }]}><Pressable accessibilityLabel="Back to planner" style={styles.headerButton} onPress={() => void cancelRoute()}><Text style={styles.headerArrow}>←</Text></Pressable><View style={styles.headerCopy}><Text style={styles.headerTitle}>Trip simulation</Text><Text style={styles.headerSubtitle}>{origin?.label || 'Origin'}  →  {destination?.label || 'Destination'}</Text></View><Pressable accessibilityRole="button" style={styles.headerButton} onPress={() => void cancelRoute('preferences')}><Text style={styles.edit}>Edit</Text></Pressable></View> : null}
    {viewMode === 'input' ? <View style={[StyleSheet.absoluteFill, styles.inputSheetHost, searchMode ? styles.hiddenWhilePicking : null]} pointerEvents="box-none"><RouteBottomSheet bottom={bottomOffset} scroll={sheetMode === 'expanded'} scrollToY={plannerFocus === 'preferences' ? 520 : plannerFocus === 'battery' ? 250 : undefined}><TripInputScreen expanded={sheetMode === 'expanded'} origin={origin} destination={destination} currentSocPct={currentSocPct} socInputText={socInputText} manualVehicle={manualVehicle} preferences={preferences} minimumArrivalSocPct={minimumArrivalSocPct} fieldErrors={fieldErrors} routeError={routeError} onOpenPlanner={() => { setPlannerFocus(null); setSheetMode('expanded'); }} onClosePlanner={() => setSheetMode('peek')} onOpenOriginSearch={() => setSearchMode('origin')} onOpenDestinationSearch={() => setSearchMode('destination')} onChangeSocText={changeSocText} onQuickSelectSoc={selectSoc} onManualVehicleChange={(vehicle) => updateField('vehicle', () => setManualVehicle(vehicle))} onPreferencesChange={(value) => updateField('preferences', () => setPreferences(value))} onMinimumArrivalSocChange={(value) => updateField('minimum_arrival_soc_pct', () => setMinimumArrivalSocPct(value))} onVehicleProfile={setProfileVehicle} onSimulate={() => void simulateRoute().catch(() => undefined)} isSimulating={isSimulating} /></RouteBottomSheet></View> : null}
    {viewMode === 'completed' ? <RouteBottomSheet bottom={bottomOffset} scroll={false}><Text style={styles.completedTitle}>Destination reached</Text><Text style={styles.completedText}>Navigation stopped and temporary route data deletion started.</Text><Pressable accessibilityRole="button" style={styles.completedButton} onPress={() => { setViewMode('input'); setSheetMode('peek'); }}><Text style={styles.completedButtonText}>Plan another trip</Text></Pressable></RouteBottomSheet> : null}
    {viewMode === 'simulation' && simulationResult ? <TripSimulationScreen result={simulationResult} expanded={resultExpanded} onToggleExpanded={() => setResultExpanded((value) => !value)} onEditTrip={() => void cancelRoute('preferences')} onCancel={() => cancelRoute()} onChooseAnotherRoute={async () => { setPreferences((value) => ({ ...value, route_type: value.route_type === 'fastest' ? 'shortest' : 'fastest' })); await cancelRoute(); }} onAdjustPreferences={() => cancelRoute('preferences')} onChargeBeforeDeparture={() => cancelRoute('battery')} onStartNavigation={startNavigation} onAddStopToRoute={simulateRoute} originLabel={origin?.label || 'Origin'} destinationLabel={destination?.label || 'Destination'} preferences={preferences} minimumArrivalSocPct={minimumArrivalSocPct} isRecalculating={isSimulating} bottomOffset={bottomOffset} topInset={topInset} /> : null}
    <DestinationSearchModal visible={Boolean(searchMode)} mode={searchMode ?? 'destination'} onClose={() => setSearchMode(null)} onSelect={selectLocation} onNetworkError={() => setConnectionError(true)} onConnectionRestored={() => setConnectionError(false)} originLat={origin?.latitude} originLon={origin?.longitude} pickedPoint={pickedPoint} bottomOffset={bottomOffset} />
    <RouteDialog visible={Boolean(locationDialog)} title={locationDialog === 'gps_error' ? 'Location unavailable' : 'Location access needed'} primaryLabel="Allow location" onPrimary={() => void requestLocation()} secondaryLabel="Enter origin manually" onSecondary={() => { setLocationDialog(null); setSearchMode('origin'); setSheetMode('expanded'); }}><Text style={styles.dialogText}>{locationDialog === 'gps_error' ? 'GPS could not determine your location. Retry or choose a starting point manually.' : 'EV-FLOW uses your location as the route origin. Raw coordinates are not stored by the frontend.'}</Text><Text style={styles.dialogHint}>You can continue without granting permission.</Text></RouteDialog>
    <RouteDialog visible={connectionError} title="Lost connection" primaryLabel="Retry" onPrimary={() => { if (retryRef.current) retryRef.current(); else void checkRouteApiHealth().then(() => setConnectionError(false)).catch(() => setConnectionError(true)); }} secondaryLabel={Platform.OS === 'web' ? 'Close' : 'Connection settings'} onSecondary={() => Platform.OS === 'web' ? setConnectionError(false) : void Linking.openSettings()}><Text style={styles.dialogText}>Check your mobile or wireless connection. Your current route state remains in memory.</Text></RouteDialog>
  </View>;
}

const styles = StyleSheet.create({
  shell: { flex: 1, backgroundColor: routeColors.mapFallback },
  // Host keeps TripInputScreen mounted (its profile fetch and vehicle choice
  // live there) while the search sheet needs the map area completely clear.
  inputSheetHost: { zIndex: 20 }, hiddenWhilePicking: { display: 'none' },
  searchCard: { position: 'absolute', left: 16, right: 16, minHeight: 62, borderRadius: routeRadius.lg, backgroundColor: routeColors.surface, paddingHorizontal: routeSpacing.md, flexDirection: 'row', alignItems: 'center', gap: routeSpacing.md, zIndex: 10, ...routeShadow },
  searchIcon: { color: routeColors.brand, fontSize: 24 }, searchLabel: { color: routeColors.textSecondary, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }, searchText: { color: routeColors.textSecondary, fontSize: 14, marginTop: 2 }, more: { marginLeft: 'auto', color: routeColors.textSecondary, fontSize: 22 },
  rangeBadge: { position: 'absolute', left: 18, backgroundColor: routeColors.surface, borderRadius: routeRadius.pill, paddingHorizontal: 12, paddingVertical: 8, zIndex: 10, ...routeShadow }, rangeText: { color: routeColors.brand, fontWeight: '800', fontSize: 11 },
  mapControls: { position: 'absolute', right: 16, width: 46, backgroundColor: routeColors.surface, borderRadius: routeRadius.lg, zIndex: 10, ...routeShadow }, mapControl: { width: 46, minHeight: 46, alignItems: 'center', justifyContent: 'center' }, mapControlText: { color: routeColors.brand, fontSize: 22 }, controlDivider: { height: 1, backgroundColor: routeColors.border, marginHorizontal: 10 },
  routeHeader: { position: 'absolute', left: 16, right: 16, minHeight: 58, backgroundColor: routeColors.surface, borderRadius: routeRadius.lg, flexDirection: 'row', alignItems: 'center', paddingHorizontal: routeSpacing.sm, zIndex: 10, ...routeShadow }, headerButton: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' }, headerArrow: { fontSize: 24 }, headerCopy: { flex: 1, alignItems: 'center' }, headerTitle: { color: routeColors.textPrimary, fontWeight: '800', fontSize: 13 }, headerSubtitle: { color: routeColors.textSecondary, fontSize: 9, marginTop: 2 }, edit: { color: routeColors.brand, fontWeight: '800', fontSize: 11 },
  dialogText: { color: routeColors.textSecondary, lineHeight: 18 }, dialogHint: { color: routeColors.textSecondary, fontSize: 10 },
  completedTitle: { color: routeColors.success, fontWeight: '800', fontSize: 20 }, completedText: { color: routeColors.textSecondary, marginTop: 6 }, completedButton: { minHeight: 48, borderRadius: routeRadius.md, backgroundColor: routeColors.brand, alignItems: 'center', justifyContent: 'center', marginTop: routeSpacing.md }, completedButtonText: { color: '#FFFFFF', fontWeight: '800' },
});
