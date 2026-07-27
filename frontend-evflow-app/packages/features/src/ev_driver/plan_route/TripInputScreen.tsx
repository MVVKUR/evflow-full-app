import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { useNavigate } from 'react-router';
import { fetchEvModels, getMe, reverseGeocode, type EVModelApiItem, type ManualVehicleInput, type RoutePreferencesInput, type UserPublic } from '@evflow/shared';
import { getUserLocation } from '../utils/location';
import { BatteryLevelInput } from './BatteryLevelInput';
import type { LocationState } from './planRouteTypes';

type TripInputScreenProps = {
  origin: LocationState | null;
  destination: LocationState | null;
  currentSocPct: number;
  socInputText: string;
  manualVehicle: ManualVehicleInput;
  preferences: Required<RoutePreferencesInput>;
  minimumArrivalSocPct: number;
  onSetOrigin: (loc: LocationState) => void;
  onOpenDestinationSearch: () => void;
  onChangeSocText: (text: string) => void;
  onQuickSelectSoc: (val: number) => void;
  onManualVehicleChange: (vehicle: ManualVehicleInput) => void;
  onPreferencesChange: (preferences: Required<RoutePreferencesInput>) => void;
  onMinimumArrivalSocChange: (value: number) => void;
  onVehicleProfileAvailable: (available: boolean) => void;
  onSimulate: () => void;
  isSimulating: boolean;
  error?: string | null;
};

export function TripInputScreen({
  origin,
  destination,
  currentSocPct,
  socInputText,
  manualVehicle,
  preferences,
  minimumArrivalSocPct,
  onSetOrigin,
  onOpenDestinationSearch,
  onChangeSocText,
  onQuickSelectSoc,
  onManualVehicleChange,
  onPreferencesChange,
  onMinimumArrivalSocChange,
  onVehicleProfileAvailable,
  onSimulate,
  isSimulating,
  error,
}: TripInputScreenProps) {
  const navigate = useNavigate();

  const [user, setUser] = useState<UserPublic | null>(null);
  const [selectedEvModel, setSelectedEvModel] = useState<EVModelApiItem | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [locationDenied, setLocationDenied] = useState(false);
  const [manualOrigin, setManualOrigin] = useState('');

  // Auto-fill origin from location helper & reverse geocode to location name
  useEffect(() => {
    let mounted = true;
    getUserLocation({ requestPermission: true }).then((res) => {
      if (!mounted) return;
      if (res.coordinates) {
        const { latitude, longitude } = res.coordinates;
        onSetOrigin({
          latitude,
          longitude,
          label: 'Current Location — Detecting location name...',
        });

        reverseGeocode(latitude, longitude).then((rev) => {
          if (!mounted) return;
          const locationName = rev.label || rev.city || 'Indonesia';
          onSetOrigin({
            latitude,
            longitude,
            label: `Current Location — ${locationName}`,
          });
        });
      } else if (!origin) setLocationDenied(true);
    });

    return () => {
      mounted = false;
    };
  }, []);



  // Load user profile & selected EV model specs
  useEffect(() => {
    let mounted = true;

    async function loadData() {
      try {
        const u = await getMe();
        if (!mounted) return;
        setUser(u);

        if (u.ev_model_id) {
          const res = await fetchEvModels({ limit: 300 });
          if (!mounted) return;
          const found = res.items.find((m) => m.id === u.ev_model_id);
          if (found) {
            setSelectedEvModel(found);
            onVehicleProfileAvailable(true);
          } else {
            onVehicleProfileAvailable(false);
          }
        } else {
          onVehicleProfileAvailable(false);
        }
      } catch (e) {
        // Handle unauthenticated or network error
        onVehicleProfileAvailable(false);
      } finally {
        if (mounted) setLoadingProfile(false);
      }
    }

    loadData();

    return () => {
      mounted = false;
    };
  }, []);

  // Calculate estimated range from selected EV model and current SoC
  const estimatedRangeKm = React.useMemo(() => {
    if (!selectedEvModel || !selectedEvModel.range_km) return null;
    return Math.round(selectedEvModel.range_km * (currentSocPct / 100.0) * 0.85);
  }, [selectedEvModel, currentSocPct]);

  const missingEvModel = !loadingProfile && (!user?.ev_model_id || !selectedEvModel);
  const canSimulate = Boolean(
    origin &&
      destination &&
      (selectedEvModel || manualVehicle.usable_range_km > 0) &&
      currentSocPct >= 0 &&
      currentSocPct <= 100 &&
      !isSimulating
  );

  function updateManualNumber(field: keyof ManualVehicleInput, text: string) {
    const value = Number(text.replace(/[^0-9.]/g, ''));
    onManualVehicleChange({ ...manualVehicle, [field]: Number.isFinite(value) ? value : 0 });
  }

  function applyManualOrigin() {
    const [lat, lon] = manualOrigin.split(',').map((part) => Number(part.trim()));
    if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
      onSetOrigin({ latitude: lat, longitude: lon, label: 'Manual origin' });
      setLocationDenied(false);
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Plan Route</Text>
        <Text style={styles.subtitle}>Simulate energy use for your trip</Text>
      </View>

      {/* Origin and Destination Card */}
      <View style={styles.routeCard}>
        <View style={styles.routeRow}>
          <View style={styles.iconCircleOrigin}>
            <View style={styles.innerDotGreen} />
          </View>
          <View style={styles.routeTextWrap}>
            <Text style={styles.fieldLabel}>FROM</Text>
            <Text style={styles.fieldValue} numberOfLines={1}>
              {origin ? origin.label : 'Detecting current location...'}
            </Text>
          </View>
        </View>

        <View style={styles.divider} />

        <Pressable style={styles.routeRow} onPress={onOpenDestinationSearch}>
          <View style={styles.iconCircleDest}>
            <Text style={styles.destPinSymbol}>📍</Text>
          </View>
          <View style={styles.routeTextWrap}>
            <Text style={styles.fieldLabel}>TO</Text>
            <Text
              style={[styles.fieldValue, !destination && styles.placeholderValue]}
              numberOfLines={1}
            >
              {destination ? destination.label : 'Where are you going?'}
            </Text>
          </View>
        </Pressable>
      </View>

      {locationDenied && !origin ? <View style={styles.permissionBox}>
        <Text style={styles.warningTitle}>Location permission is unavailable</Text>
        <Text style={styles.warningSub}>Enter your starting coordinates to plan this trip.</Text>
        <View style={styles.manualOriginRow}><TextInput accessibilityLabel="Manual origin latitude and longitude" value={manualOrigin} onChangeText={setManualOrigin} placeholder="-6.2088, 106.8456" style={styles.manualOriginInput} /><Pressable accessibilityLabel="Use manual origin" onPress={applyManualOrigin} style={styles.manualOriginButton}><Text style={styles.manualOriginButtonText}>Use</Text></Pressable></View>
      </View> : null}

      {/* Vehicle Profile Warning Banner if no EV model selected */}
      {missingEvModel ? (
        <View style={styles.warningBanner}>
          <Text style={styles.warningIcon}>⚠️</Text>
          <View style={styles.warningTextWrap}>
            <Text style={styles.warningTitle}>No EV Model Selected</Text>
            <Text style={styles.warningSub}>
              Enter your usable range below or select a saved vehicle profile.
            </Text>
            <Pressable
              style={styles.profileLinkButton}
              onPress={() => navigate('/ev-driver/profile')}
            >
              <Text style={styles.profileLinkText}>Select Vehicle Profile →</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {missingEvModel ? <View style={styles.settingsSection}>
        <Text style={styles.sectionTitle}>Manual vehicle</Text>
        <Text style={styles.inputLabel}>Usable range (km) *</Text>
        <TextInput accessibilityLabel="Manual usable vehicle range" keyboardType="decimal-pad" value={manualVehicle.usable_range_km ? String(manualVehicle.usable_range_km) : ''} onChangeText={(text) => updateManualNumber('usable_range_km', text)} placeholder="350" style={styles.settingsInput} />
        <View style={styles.twoColumns}><View style={styles.column}><Text style={styles.inputLabel}>Battery capacity (kWh)</Text><TextInput accessibilityLabel="Manual battery capacity" keyboardType="decimal-pad" value={manualVehicle.battery_kwh ? String(manualVehicle.battery_kwh) : ''} onChangeText={(text) => updateManualNumber('battery_kwh', text)} placeholder="60" style={styles.settingsInput} /></View><View style={styles.column}><Text style={styles.inputLabel}>Maximum charge (kW)</Text><TextInput accessibilityLabel="Manual maximum charging power" keyboardType="decimal-pad" value={manualVehicle.max_dc_charge_kw ? String(manualVehicle.max_dc_charge_kw) : ''} onChangeText={(text) => updateManualNumber('max_dc_charge_kw', text)} placeholder="150" style={styles.settingsInput} /></View></View>
        <Text style={styles.inputLabel}>Connector type</Text><TextInput accessibilityLabel="Manual connector type" autoCapitalize="characters" value={manualVehicle.connector_type || ''} onChangeText={(connector_type) => onManualVehicleChange({ ...manualVehicle, connector_type })} placeholder="CCS2" style={styles.settingsInput} />
      </View> : null}

      {/* Battery Level Input Card */}
      <BatteryLevelInput
        value={currentSocPct}
        inputText={socInputText}
        onChangeText={onChangeSocText}
        onQuickSelect={onQuickSelectSoc}
        estimatedRangeKm={estimatedRangeKm}
      />

      <View style={styles.settingsSection}>
        <Text style={styles.sectionTitle}>Route preferences</Text>
        <Text style={styles.inputLabel}>Route type</Text>
        <View style={styles.segmented}>{(['fastest', 'shortest'] as const).map((routeType) => <Pressable key={routeType} accessibilityRole="radio" accessibilityState={{ checked: preferences.route_type === routeType }} style={[styles.segment, preferences.route_type === routeType && styles.segmentActive]} onPress={() => onPreferencesChange({ ...preferences, route_type: routeType })}><Text style={[styles.segmentText, preferences.route_type === routeType && styles.segmentTextActive]}>{routeType === 'fastest' ? 'Fastest' : 'Shortest'}</Text></Pressable>)}</View>
        <View style={styles.twoColumns}><View style={styles.column}><Text style={styles.inputLabel}>Maximum detour (km)</Text><TextInput accessibilityLabel="Maximum charging detour" keyboardType="decimal-pad" value={String(preferences.maximum_detour_km)} onChangeText={(text) => onPreferencesChange({ ...preferences, maximum_detour_km: Math.max(1, Math.min(50, Number(text) || 1)) })} style={styles.settingsInput} /></View><View style={styles.column}><Text style={styles.inputLabel}>Arrival reserve (%)</Text><TextInput accessibilityLabel="Minimum arrival battery" keyboardType="decimal-pad" value={String(minimumArrivalSocPct)} onChangeText={(text) => onMinimumArrivalSocChange(Math.max(0, Math.min(50, Number(text) || 0)))} style={styles.settingsInput} /></View></View>
        <View style={styles.toggleRow}><View><Text style={styles.toggleLabel}>Prefer fast charging</Text><Text style={styles.toggleHelp}>Prioritise higher-power compatible stations</Text></View><Switch accessibilityLabel="Prefer fast charging" value={preferences.prefer_fast_charging} onValueChange={(prefer_fast_charging) => onPreferencesChange({ ...preferences, prefer_fast_charging })} trackColor={{ false: '#CBD5E1', true: '#5EEAD4' }} thumbColor={preferences.prefer_fast_charging ? '#00696F' : '#FFFFFF'} /></View>
      </View>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorBoxText}>{error}</Text>
        </View>
      ) : null}

      {/* Simulate Route Action Button */}
      <Pressable
        style={[styles.simulateButton, !canSimulate && styles.simulateButtonDisabled]}
        onPress={onSimulate}
        disabled={!canSimulate}
      >
        {isSimulating ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <Text style={styles.simulateButtonText}>⚡ Simulate Route</Text>
        )}
      </Pressable>

      <View style={styles.encryptionNoteRow}>
        <Text style={styles.lockIcon}>🔒</Text>
        <Text style={styles.encryptionNoteText}>
          Your route & battery data are encrypted for this trip only
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 24,
  },
  header: {
    marginBottom: 20,
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    color: '#0F172A',
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: 15,
    color: '#64748B',
    marginTop: 4,
  },
  routeCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 12,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
  settingsSection: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 8, padding: 14, marginBottom: 16, gap: 8 },
  sectionTitle: { color: '#0F172A', fontSize: 17, fontWeight: '800', marginBottom: 2 },
  inputLabel: { color: '#475569', fontSize: 12, fontWeight: '700' },
  settingsInput: { minHeight: 44, borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 6, paddingHorizontal: 10, color: '#0F172A' },
  twoColumns: { flexDirection: 'row', gap: 10 },
  column: { flex: 1, gap: 6 },
  segmented: { flexDirection: 'row', borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 6, overflow: 'hidden' },
  segment: { flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', backgroundColor: '#FFFFFF' },
  segmentActive: { backgroundColor: '#00696F' },
  segmentText: { color: '#334155', fontWeight: '700' },
  segmentTextActive: { color: '#FFFFFF' },
  toggleRow: { minHeight: 52, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  toggleLabel: { color: '#0F172A', fontWeight: '700' },
  toggleHelp: { color: '#64748B', fontSize: 12 },
  permissionBox: { backgroundColor: '#FFFBEB', borderWidth: 1, borderColor: '#FDE68A', borderRadius: 8, padding: 14, marginBottom: 16 },
  manualOriginRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  manualOriginInput: { flex: 1, minHeight: 44, borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 6, paddingHorizontal: 10 },
  manualOriginButton: { minWidth: 52, minHeight: 44, backgroundColor: '#00696F', borderRadius: 6, alignItems: 'center', justifyContent: 'center' },
  manualOriginButtonText: { color: '#FFFFFF', fontWeight: '700' },
  routeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
  },
  iconCircleOrigin: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 2,
    borderColor: '#00696F',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
  },
  innerDotGreen: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#00696F',
  },
  iconCircleDest: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
  },
  destPinSymbol: {
    fontSize: 18,
  },
  routeTextWrap: {
    flex: 1,
  },
  fieldLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: '#94A3B8',
    letterSpacing: 0.8,
  },
  fieldValue: {
    fontSize: 15,
    fontWeight: '600',
    color: '#0F172A',
    marginTop: 2,
  },
  placeholderValue: {
    color: '#94A3B8',
  },
  divider: {
    height: 1,
    backgroundColor: '#F1F5F9',
    marginVertical: 4,
  },
  warningBanner: {
    flexDirection: 'row',
    backgroundColor: '#FFFBEB',
    borderWidth: 1,
    borderColor: '#FCD34D',
    borderRadius: 14,
    padding: 14,
    marginBottom: 16,
  },
  warningIcon: {
    fontSize: 20,
    marginRight: 12,
  },
  warningTextWrap: {
    flex: 1,
  },
  warningTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#B45309',
  },
  warningSub: {
    fontSize: 13,
    color: '#92400E',
    marginTop: 2,
  },
  profileLinkButton: {
    marginTop: 8,
  },
  profileLinkText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#D97706',
  },
  errorBox: {
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  errorBoxText: {
    fontSize: 13,
    color: '#DC2626',
    fontWeight: '600',
  },
  simulateButton: {
    backgroundColor: '#00696F',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#00696F',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 4,
    marginBottom: 12,
  },
  simulateButtonDisabled: {
    backgroundColor: '#94A3B8',
    shadowOpacity: 0,
    elevation: 0,
  },
  simulateButtonText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  encryptionNoteRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  lockIcon: {
    fontSize: 12,
    marginRight: 6,
  },
  encryptionNoteText: {
    fontSize: 12,
    color: '#64748B',
  },
});
