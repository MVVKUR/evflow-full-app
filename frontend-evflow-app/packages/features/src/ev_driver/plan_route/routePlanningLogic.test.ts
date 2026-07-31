import { describe, expect, it } from 'vitest';
import { buildRouteRequest, canStartNavigation, choiceForPreferences, clearFieldError, formatRouteEta, hasUsableVehicle, locationEntryDecision, noStationActions, noSuitableStationReasons, nonIncreasingDrivingSoc, preferencesForChoice, routePresentation, suitableActiveStops, validateRouteInput } from './routePlanningLogic';

describe('route request inputs', () => {
  it('allows a positive manual range without an EV profile', () => {
    expect(hasUsableVehicle(false, { usable_range_km: 350 })).toBe(true);
    expect(hasUsableVehicle(false, { usable_range_km: 0 })).toBe(false);
  });

  it('submits manual vehicle and all charging preferences', () => {
    const request = buildRouteRequest({
      origin: { latitude: -6.2, longitude: 106.8 },
      destination: { latitude: -6.9, longitude: 107.6 },
      currentSocPct: 72,
      minimumArrivalSocPct: 20,
      preferences: { route_type: 'shortest', maximum_detour_km: 9, prefer_fast_charging: false },
      manualVehicle: { usable_range_km: 350, battery_kwh: 60, connector_type: 'CCS2' },
    });
    expect(request.vehicle?.usable_range_km).toBe(350);
    expect(request.preferences).toEqual({ route_type: 'shortest', maximum_detour_km: 9, prefer_fast_charging: false });
    expect(request.minimum_arrival_soc_pct).toBe(20);
  });

  it('submits the selected vehicle profile id without duplicating its battery model', () => {
    const request = buildRouteRequest({ origin: { latitude: -6.2, longitude: 106.8 }, destination: { latitude: -6.5, longitude: 107 }, currentSocPct: 72, minimumArrivalSocPct: 20, preferences: { route_type: 'fastest', maximum_detour_km: 15, prefer_fast_charging: true }, evModelId: 'vehicle-model-7' });
    expect(request.ev_model_id).toBe('vehicle-model-7');
    expect(request.vehicle).toBeUndefined();
  });

  it('uses estimated current SoC for rerouting, never projected arrival SoC', () => {
    const request = buildRouteRequest({
      origin: { latitude: -6.4, longitude: 107 }, destination: { latitude: -6.9, longitude: 107.6 },
      currentSocPct: 61, minimumArrivalSocPct: 20,
      preferences: { route_type: 'fastest', maximum_detour_km: 15, prefer_fast_charging: true },
    });
    const projectedArrivalSoc = 18;
    expect(request.current_soc_pct).toBe(61);
    expect(request.current_soc_pct).not.toBe(projectedArrivalSoc);
  });
  it('renders every backend no-station action', () => {
    expect(noStationActions(['choose_another_route', 'adjust_preferences', 'charge_before_departure']).map((action) => action.label)).toEqual(['Choose another route', 'Adjust preferences', 'Charge before departure']);
  });
  it('shows a plan ETA before active evaluation and handles missing ETA', () => {
    expect(formatRouteEta('2026-07-27T10:30:00Z')).toMatch(/^Arrives /);
    expect(formatRouteEta(null)).toBe('ETA unavailable');
  });
  it('offers Add Stop only for compatible stations with a free connector', () => {
    const station = { id: 'station', name: 'Station', latitude: -6, longitude: 106, connector_types: [], connectors: [], sources: [], address: null, province: null, city: null, operator: null, power_kw: 50, charge_type: null, speed_tier: null, connector_inferred: false, status: 'operational', date_verified: null, distance_km: null } as any;
    const stop = { station, distance_from_origin_km: 5, detour_km: 1, arrival_soc_pct: 20, recommended_target_soc_pct: 80, energy_to_add_kwh: 20, estimated_charging_minutes: 20, effective_charging_power_kw: 50, availability: 'available_now', data_confidence: 'high' };
    expect(suitableActiveStops([{ ...stop, connector_compatible: true, available_connector_count: 1 }, { ...stop, connector_compatible: false, available_connector_count: 1 }, { ...stop, connector_compatible: true, available_connector_count: 0 }] as any)).toHaveLength(1);
  });
  it('accepts decreasing backend current SoC and rejects increases while driving', () => {
    expect(nonIncreasingDrivingSoc(72, 68)).toBe(68);
    expect(nonIncreasingDrivingSoc(68, 70)).toBe(68);
  });

  it('validates every local route field and keeps valid user input intact', () => {
    const same = { latitude: -6.2, longitude: 106.8 };
    expect(validateRouteInput({ origin: same, destination: same, currentSocPct: 120, minimumArrivalSocPct: 55, hasVehicle: false })).toEqual({
      current_soc_pct: 'Enter a battery level from 0% to 100%.',
      minimum_arrival_soc_pct: 'Reserve must be from 0% to 50%.',
      vehicle: 'Select a vehicle profile or enter a usable range above zero.',
      destination: 'Destination must be different from the origin.',
    });
    expect(clearFieldError({ destination: 'bad', vehicle: 'missing' }, 'destination')).toEqual({ vehicle: 'missing' });
  });

  it('maps all three preference controls into the existing backend contract', () => {
    const current = { route_type: 'fastest', maximum_detour_km: 15, prefer_fast_charging: true };
    expect(preferencesForChoice('fastest', current)).toMatchObject({ route_type: 'fastest', prefer_fast_charging: true });
    expect(preferencesForChoice('least_detour', current)).toMatchObject({ route_type: 'shortest', prefer_fast_charging: false });
    expect(preferencesForChoice('available_now', current)).toMatchObject({ route_type: 'fastest', prefer_fast_charging: false });
    expect(choiceForPreferences(preferencesForChoice('available_now', current))).toBe('available_now');
  });

  it('preserves backend station ordering and only filters explicit active-stop safety failures', () => {
    const station = { id: 'a', connector_types: [], connectors: [], sources: [] } as any;
    const stop = (id: string) => ({ station: { ...station, id }, connector_compatible: true, available_connector_count: 1 } as any);
    expect(suitableActiveStops([stop('rank-1'), stop('rank-2'), stop('rank-3')]).map((value) => value.station.id)).toEqual(['rank-1', 'rank-2', 'rank-3']);
  });

  it('derives safe no-station explanations only from backend candidate evidence', () => {
    expect(noSuitableStationReasons([{ detour_within_budget: false, connector_compatible: false, available_connector_count: 0 } as any])).toEqual([
      'Some stations exceed the reachable detour corridor.',
      'Some stations lack a compatible connector.',
    ]);
  });

  it('derives direct, recommended, added, and no-station UI from backend response state', () => {
    const base = { route_status: 'charging_required', directly_reachable: false, user_requested_stop: null, warning: null } as any;
    expect(routePresentation({ ...base, route_status: 'direct_route_available', directly_reachable: true })).toBe('direct');
    expect(routePresentation(base)).toBe('charging_recommended');
    expect(routePresentation({ ...base, user_requested_stop: { station: { id: 's' } } })).toBe('charging_added');
    expect(routePresentation({ ...base, warning: { code: 'no_suitable_station' } })).toBe('no_suitable_station');
    expect(canStartNavigation(base)).toBe(false);
    expect(canStartNavigation({ ...base, user_requested_stop: { station: { id: 's' } } })).toBe(true);
  });

  it('submits a selected alternative as waypoint_station_id', () => {
    const request = buildRouteRequest({ origin: { latitude: -6.2, longitude: 106.8 }, destination: { latitude: -6.6, longitude: 107.2 }, currentSocPct: 40, minimumArrivalSocPct: 20, preferences: { route_type: 'fastest', maximum_detour_km: 15, prefer_fast_charging: true }, waypointStationId: 'server-ranked-alternative-2' });
    expect(request.waypoint_station_id).toBe('server-ranked-alternative-2');
  });

  it('offers manual origin after permission denial or GPS failure', () => {
    expect(locationEntryDecision('granted', true)).toBe('use_location');
    expect(locationEntryDecision('undetermined', false)).toBe('request_permission');
    expect(locationEntryDecision('denied', false)).toBe('manual_or_retry');
    expect(locationEntryDecision('gps_error', false)).toBe('manual_or_retry');
  });
});
