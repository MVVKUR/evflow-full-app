import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { fetchEvModels, getMe, type EVModelApiItem, type ManualVehicleInput, type RoutePreferencesInput, type UserPublic } from '@evflow/shared';
import { PlatformSlider } from '../../shared/PlatformSlider';
import { RouteFieldError } from './components/RouteFieldError';
import { choiceForPreferences, preferencesForChoice, type ChargingPreference, type RouteInputErrors } from './routePlanningLogic';
import { routeColors, routeRadius, routeSpacing } from './routeTheme';
import type { LocationState } from './planRouteTypes';

export type VehicleDisplay = { id?: string; name: string; usableRangeKm: number; source: 'profile' | 'manual' };

type Props = {
  expanded: boolean;
  origin: LocationState | null;
  destination: LocationState | null;
  currentSocPct: number;
  socInputText: string;
  manualVehicle: ManualVehicleInput;
  preferences: Required<RoutePreferencesInput>;
  minimumArrivalSocPct: number;
  fieldErrors: RouteInputErrors;
  routeError?: string | null;
  onOpenPlanner: () => void;
  onClosePlanner: () => void;
  onOpenOriginSearch: () => void;
  onOpenDestinationSearch: () => void;
  onChangeSocText: (text: string) => void;
  onQuickSelectSoc: (value: number) => void;
  onManualVehicleChange: (vehicle: ManualVehicleInput) => void;
  onPreferencesChange: (preferences: Required<RoutePreferencesInput>) => void;
  onMinimumArrivalSocChange: (value: number) => void;
  onVehicleProfile: (vehicle: VehicleDisplay | null) => void;
  onSimulate: () => void;
  isSimulating: boolean;
};

export function TripInputScreen(props: Props) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [selectedEvModel, setSelectedEvModel] = useState<EVModelApiItem | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const nextUser = await getMe();
        if (!mounted) return;
        setUser(nextUser);
        if (nextUser.ev_model_id) {
          const models = await fetchEvModels({ limit: 300 });
          if (!mounted) return;
          const model = models.items.find((item) => item.id === nextUser.ev_model_id) ?? null;
          setSelectedEvModel(model);
          props.onVehicleProfile(model ? { id: model.id, name: model.name, usableRangeKm: model.range_km || 0, source: 'profile' } : null);
        } else props.onVehicleProfile(null);
      } catch { if (mounted) props.onVehicleProfile(null); }
      finally { if (mounted) setLoadingProfile(false); }
    })();
    return () => { mounted = false; };
  }, []);

  const vehicle = selectedEvModel
    ? { id: selectedEvModel.id, name: selectedEvModel.name, usableRangeKm: selectedEvModel.range_km || 0, source: 'profile' as const }
    : props.manualVehicle.usable_range_km > 0
      ? { name: props.manualVehicle.name || 'Manual EV', usableRangeKm: props.manualVehicle.usable_range_km, source: 'manual' as const }
      : null;
  const choice = choiceForPreferences(props.preferences);
  const disabled = props.isSimulating || Object.keys(props.fieldErrors).length > 0;

  if (!props.expanded) return <View>
    <View style={styles.peekHeader}><View><Text style={styles.peekTitle}>Plan route</Text><Text style={styles.peekPath}>{props.origin ? 'Current location' : 'Choose origin'}  →  {props.destination?.label || 'Choose destination'}</Text></View></View>
    <View style={styles.badges}><View style={styles.brandPill}><Text style={styles.brandPillText}>{vehicle?.name || 'Select vehicle'}</Text></View><View style={styles.pill}><Text style={styles.pillText}>{props.minimumArrivalSocPct}% reserve</Text></View></View>
    <Pressable accessibilityRole="button" accessibilityLabel="Open route planner" style={styles.primary} onPress={props.onOpenPlanner}><Text style={styles.primaryText}>Open route planner</Text></Pressable>
  </View>;

  return <View>
    <View style={styles.titleRow}><Text style={styles.title}>{props.routeError || Object.keys(props.fieldErrors).length ? 'Fix route details' : 'Plan route'}</Text><Pressable accessibilityRole="button" style={styles.closeButton} onPress={props.onClosePlanner}><Text style={styles.closeText}>Close</Text></Pressable></View>
    {props.routeError || Object.keys(props.fieldErrors).length ? <Text style={styles.subtitle}>Review the highlighted fields before simulation.</Text> : null}

    <Pressable accessibilityRole="button" accessibilityLabel="Choose origin" style={[styles.field, props.fieldErrors.origin && styles.fieldError]} onPress={props.onOpenOriginSearch}>
      <Text style={styles.label}>From</Text><Text style={styles.fieldText} numberOfLines={1}>●  {props.origin?.label || 'Choose starting location'}</Text>
    </Pressable><RouteFieldError message={props.fieldErrors.origin} />
    <Pressable accessibilityRole="button" accessibilityLabel="Choose destination" style={[styles.field, props.fieldErrors.destination && styles.fieldError]} onPress={props.onOpenDestinationSearch}>
      <Text style={styles.label}>To</Text><Text style={styles.fieldText} numberOfLines={1}>⌖  {props.destination?.label || 'Where are you going?'}</Text>
    </Pressable><RouteFieldError message={props.fieldErrors.destination} />

    <View style={[styles.profile, props.fieldErrors.vehicle && styles.fieldError]}>
      <View><Text style={styles.label}>Vehicle profile</Text>{loadingProfile ? <ActivityIndicator color={routeColors.brand} /> : <Text style={styles.profileText}>{vehicle ? `${vehicle.name} · ${Math.round(vehicle.usableRangeKm)} km usable` : 'No vehicle selected'}</Text>}<Text style={styles.source}>{vehicle ? `${vehicle.source} vehicle source` : 'Enter a manual usable range below'}</Text></View>
    </View><RouteFieldError message={props.fieldErrors.vehicle} />
    {!selectedEvModel ? <TextInput accessibilityLabel="Manual usable vehicle range" keyboardType="decimal-pad" value={props.manualVehicle.usable_range_km ? String(props.manualVehicle.usable_range_km) : ''} onChangeText={(text) => props.onManualVehicleChange({ ...props.manualVehicle, usable_range_km: Number(text.replace(/[^0-9.]/g, '')) || 0 })} placeholder="Usable range in km" style={styles.manualInput} /> : null}

    <View style={[styles.section, props.fieldErrors.current_soc_pct && styles.fieldError]}><View style={styles.sectionHeader}><Text style={styles.label}>Current battery</Text><TextInput accessibilityLabel="Current battery percentage" keyboardType="numeric" value={props.socInputText} onChangeText={props.onChangeSocText} style={styles.socInput} /><Text style={styles.socSuffix}>% · {vehicle ? Math.round(vehicle.usableRangeKm * Math.max(0, Math.min(100, props.currentSocPct)) / 100) : '—'} km</Text></View>
      <PlatformSlider
        maximumTrackTintColor={routeColors.disabled}
        maximumValue={100}
        minimumTrackTintColor={routeColors.success}
        minimumValue={0}
        onValueChange={props.onQuickSelectSoc}
        step={1}
        thumbTintColor={routeColors.brand}
        value={props.currentSocPct}
      />
      <View style={styles.quickRow}>{[25, 50, 75, 100].map((value) => <Pressable key={value} accessibilityRole="radio" accessibilityState={{ selected: props.currentSocPct === value }} style={[styles.quick, props.currentSocPct === value && styles.quickSelected]} onPress={() => props.onQuickSelectSoc(value)}><Text style={[styles.quickText, props.currentSocPct === value && styles.quickTextSelected]}>{value}%</Text></Pressable>)}</View>
    </View><RouteFieldError message={props.fieldErrors.current_soc_pct} />

    <View style={[styles.reserve, props.fieldErrors.minimum_arrival_soc_pct && styles.fieldError]}><View><Text style={styles.label}>Minimum arrival battery</Text><Text style={styles.profileText}>{props.minimumArrivalSocPct}% safety reserve</Text></View><View style={styles.stepper}><Pressable accessibilityLabel="Decrease reserve" style={styles.step} onPress={() => props.onMinimumArrivalSocChange(Math.max(0, props.minimumArrivalSocPct - 5))}><Text>−</Text></Pressable><Text style={styles.reserveValue}>{props.minimumArrivalSocPct}%</Text><Pressable accessibilityLabel="Increase reserve" style={styles.step} onPress={() => props.onMinimumArrivalSocChange(Math.min(50, props.minimumArrivalSocPct + 5))}><Text>+</Text></Pressable></View></View><RouteFieldError message={props.fieldErrors.minimum_arrival_soc_pct} />

    <Text style={[styles.label, styles.preferenceLabel]}>Charging preference</Text><View style={styles.preferences}>{(['fastest', 'least_detour', 'available_now'] as ChargingPreference[]).map((value) => <Pressable key={value} accessibilityRole="radio" accessibilityState={{ selected: choice === value }} style={[styles.preference, choice === value && styles.preferenceSelected]} onPress={() => props.onPreferencesChange(preferencesForChoice(value, props.preferences))}><Text style={[styles.preferenceText, choice === value && styles.preferenceTextSelected]}>{value === 'fastest' ? 'Fastest' : value === 'least_detour' ? 'Least detour' : 'Available now'}</Text></Pressable>)}</View>
    {props.routeError ? <View style={styles.errorSummary}><Text style={styles.errorTitle}>Route simulation not generated</Text><Text style={styles.errorSummaryText}>{props.routeError}</Text></View> : null}
    <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} style={[styles.primary, disabled && styles.disabled]} onPress={props.onSimulate}>{props.isSimulating ? <ActivityIndicator color={routeColors.onBrand} /> : <Text style={styles.primaryText}>Simulate route</Text>}</Pressable>
    <Text style={styles.privacy}>Route and battery data are encrypted in transit and retained only for this trip.</Text>
  </View>;
}

const styles = StyleSheet.create({
  peekHeader: { flexDirection: 'row', justifyContent: 'space-between' }, peekTitle: { color: routeColors.textPrimary, fontSize: 20, fontWeight: '800' }, peekPath: { color: routeColors.textSecondary, fontSize: 12, marginTop: 7 },
  badges: { flexDirection: 'row', gap: routeSpacing.sm, marginVertical: routeSpacing.md }, brandPill: { backgroundColor: routeColors.brandSoft, borderRadius: routeRadius.pill, paddingHorizontal: 12, paddingVertical: 8 }, brandPillText: { color: routeColors.brandDark, fontWeight: '700', fontSize: 11 }, pill: { backgroundColor: routeColors.surfaceSecondary, borderRadius: routeRadius.pill, paddingHorizontal: 12, paddingVertical: 8 }, pillText: { color: routeColors.textSecondary, fontWeight: '700', fontSize: 11 },
  titleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, title: { color: routeColors.textPrimary, fontSize: 21, fontWeight: '800' }, subtitle: { color: routeColors.textSecondary, fontSize: 12, marginTop: 5, marginBottom: routeSpacing.md }, closeButton: { minWidth: 44, minHeight: 44, justifyContent: 'center', alignItems: 'flex-end' }, closeText: { color: routeColors.brand, fontWeight: '800', fontSize: 12 },
  field: { minHeight: 58, borderWidth: 1, borderColor: routeColors.border, borderRadius: routeRadius.md, paddingHorizontal: routeSpacing.md, justifyContent: 'center', marginTop: routeSpacing.md }, label: { color: routeColors.textSecondary, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }, fieldText: { color: routeColors.textPrimary, fontSize: 13, marginTop: 5 }, fieldError: { borderColor: routeColors.error, borderWidth: 1 },
  profile: { minHeight: 64, backgroundColor: routeColors.surfaceSecondary, borderRadius: routeRadius.md, padding: routeSpacing.md, marginTop: routeSpacing.md }, profileText: { color: routeColors.textPrimary, fontWeight: '700', fontSize: 12, marginTop: 3 }, source: { color: routeColors.textSecondary, fontSize: 9, marginTop: 2 }, manualInput: { minHeight: 48, borderWidth: 1, borderColor: routeColors.border, borderRadius: routeRadius.md, paddingHorizontal: routeSpacing.md, marginTop: routeSpacing.sm },
  section: { backgroundColor: routeColors.surfaceSecondary, borderRadius: routeRadius.md, padding: routeSpacing.md, marginTop: routeSpacing.md }, sectionHeader: { flexDirection: 'row', alignItems: 'center' }, socInput: { marginLeft: 'auto', width: 38, textAlign: 'right', color: routeColors.textPrimary, fontWeight: '800', fontSize: 17, padding: 0 }, socSuffix: { color: routeColors.textPrimary, fontWeight: '700', fontSize: 15 }, quickRow: { flexDirection: 'row', gap: routeSpacing.sm }, quick: { minHeight: 44, flex: 1, borderRadius: routeRadius.pill, backgroundColor: routeColors.control, alignItems: 'center', justifyContent: 'center' }, quickSelected: { backgroundColor: routeColors.brand }, quickText: { fontSize: 11, fontWeight: '700' }, quickTextSelected: { color: routeColors.onBrand },
  reserve: { minHeight: 58, backgroundColor: routeColors.surfaceSecondary, borderRadius: routeRadius.md, padding: routeSpacing.md, marginTop: routeSpacing.md, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, stepper: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: routeColors.border, borderRadius: routeRadius.pill }, step: { minWidth: 36, minHeight: 36, alignItems: 'center', justifyContent: 'center' }, reserveValue: { color: routeColors.brand, fontWeight: '800', fontSize: 12 },
  preferenceLabel: { marginTop: routeSpacing.md }, preferences: { flexDirection: 'row', gap: routeSpacing.sm, marginTop: routeSpacing.sm }, preference: { minHeight: 44, flex: 1, borderRadius: routeRadius.pill, backgroundColor: routeColors.surfaceSecondary, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 5 }, preferenceSelected: { backgroundColor: routeColors.brand }, preferenceText: { color: routeColors.textPrimary, fontWeight: '700', fontSize: 10 }, preferenceTextSelected: { color: routeColors.onBrand },
  errorSummary: { backgroundColor: routeColors.errorSoft, borderWidth: 1, borderColor: routeColors.errorBorder, borderRadius: routeRadius.md, padding: routeSpacing.md, marginTop: routeSpacing.md }, errorTitle: { color: routeColors.error, fontWeight: '800', fontSize: 12 }, errorSummaryText: { color: routeColors.error, fontSize: 11, marginTop: 4 },
  primary: { minHeight: 52, borderRadius: routeRadius.md, backgroundColor: routeColors.brand, alignItems: 'center', justifyContent: 'center', marginTop: routeSpacing.md }, disabled: { backgroundColor: routeColors.disabled }, primaryText: { color: routeColors.onBrand, fontWeight: '800', fontSize: 15 }, privacy: { color: routeColors.textSecondary, fontSize: 9, marginTop: routeSpacing.md },
});
