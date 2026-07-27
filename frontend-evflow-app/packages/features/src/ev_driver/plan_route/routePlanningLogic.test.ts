import { describe, expect, it } from 'vitest';
import { buildRouteRequest, formatRouteEta, hasUsableVehicle, noStationActions, nonIncreasingDrivingSoc, suitableActiveStops } from './routePlanningLogic';

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
});
