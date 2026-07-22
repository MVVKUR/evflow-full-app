import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, View } from 'react-native';
import { useLocation, useNavigate } from 'react-router';
import { fetchConnectorTypes, getAuthSession, getMe, saveAuthSession, updateProfile } from '@evflow/shared';
import { colors, onboardingStyles as styles } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';

type ConnectorOption = {
  name: string;
  count: number | null;
};

const FALLBACK_CONNECTOR_OPTIONS: readonly ConnectorOption[] = [
  { count: null, name: 'AC Type 2' },
  { count: null, name: 'CCS2' }
];

const SAVE_ERROR_MESSAGE = "Couldn't save your choice. Please try again.";

type VehicleSelectionState = {
  present: boolean;
  evModelId: string | null;
};

function vehicleSelectionFromLocationState(state: unknown): VehicleSelectionState {
  if (state && typeof state === 'object' && 'evModelId' in state) {
    const value = (state as { evModelId: unknown }).evModelId;
    return { evModelId: typeof value === 'string' ? value : null, present: true };
  }

  return { evModelId: null, present: false };
}

function stationCountLabel(count: number | null): string | null {
  return count !== null && count > 0 ? `${count.toLocaleString('en-US')} stations` : null;
}

export function ConnectorSelectScreen() {
  const navigate = useNavigate();
  const location = useLocation();
  const insets = useAppSafeAreaInsets();
  // On a page refresh the router state is gone; the screen still works, and we
  // then omit ev_model_id from the update so a previously saved car is kept.
  const vehicleSelection = vehicleSelectionFromLocationState(location.state);

  const [options, setOptions] = useState<readonly ConnectorOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [chosen, setChosen] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    fetchConnectorTypes()
      .then((items) => {
        if (!alive) {
          return;
        }

        setOptions(items.length > 0 ? items : FALLBACK_CONNECTOR_OPTIONS);
      })
      .catch((err: unknown) => {
        console.error('Failed to load connector types', err);

        if (alive) {
          setOptions(FALLBACK_CONNECTOR_OPTIONS);
        }
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });

    getMe()
      .then((user) => {
        if (alive && user.main_connector_type) {
          setChosen((current) => current ?? user.main_connector_type);
        }
      })
      .catch(() => {
        // Prefill is best-effort only; the screen works without it.
      });

    return () => {
      alive = false;
    };
  }, []);

  const goToMap = () => navigate('/ev-driver/map', { replace: true });

  const handleContinue = () => {
    if (!chosen || saving) {
      return;
    }

    setSaving(true);
    setSaveError(null);

    updateProfile(
      vehicleSelection.present
        ? { ev_model_id: vehicleSelection.evModelId, main_connector_type: chosen }
        : { main_connector_type: chosen }
    )
      .then((updated) => {
        const session = getAuthSession();

        if (session) {
          saveAuthSession({ ...session, user: updated });
        }

        goToMap();
      })
      .catch((err: unknown) => {
        console.error('Failed to save onboarding profile', err);
        setSaveError(err instanceof Error ? err.message : SAVE_ERROR_MESSAGE);
        setSaving(false);
      });
  };

  return (
    <View style={styles.page}>
      <View style={styles.contentShell}>
        <View style={[styles.header, { paddingTop: insets.top }]}>
          <Pressable
            accessibilityLabel="Back"
            accessibilityRole="button"
            onPress={() => navigate('/onboarding/vehicle')}
            style={styles.backButton}
          >
            <SvgAssetIcon color="#191C1D" height={12} name="leftChevron" width={8} />
          </Pressable>
          <Text style={styles.brand}>EV-FLOW</Text>
          <View style={styles.headerSpacer} />
        </View>

        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: 160 + insets.bottom }]}>
          <Text style={styles.title}>Which plug does your car use?</Text>
          <Text style={styles.subtitle}>We'll highlight stations that match your connector.</Text>

          {loading ? (
            <View style={styles.loadingRow}>
              <ActivityIndicator color={colors.text} size="small" />
            </View>
          ) : (
            <View style={styles.optionList}>
              {options.map((option) => (
                <ConnectorCard
                  key={option.name}
                  option={option}
                  selected={chosen === option.name}
                  onPress={() => setChosen(option.name)}
                />
              ))}
            </View>
          )}

          {saveError ? (
            <View>
              <Text style={styles.errorText}>{saveError}</Text>
              <Pressable accessibilityRole="button" onPress={handleContinue} style={styles.retryButton}>
                <Text style={styles.retryButtonText}>Retry</Text>
              </Pressable>
            </View>
          ) : null}
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: 20 + insets.bottom }]}>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: !chosen || saving }}
            disabled={!chosen || saving}
            onPress={handleContinue}
            style={[styles.continueButton, (!chosen || saving) && styles.disabledButton]}
          >
            {saving ? (
              <ActivityIndicator color={colors.white} size="small" />
            ) : (
              <Text style={styles.continueText}>Continue</Text>
            )}
          </Pressable>
          {saveError ? (
            <Text accessibilityRole="link" onPress={goToMap} style={styles.skipLink}>
              Skip for now
            </Text>
          ) : null}
        </View>
      </View>
    </View>
  );
}

type ConnectorCardProps = {
  option: ConnectorOption;
  selected: boolean;
  onPress: () => void;
};

function ConnectorCard({ option, selected, onPress }: ConnectorCardProps) {
  const countLabel = stationCountLabel(option.count);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.optionCard, selected && styles.optionCardSelected]}
    >
      <Text style={styles.optionName}>{option.name}</Text>
      {countLabel ? <Text style={styles.optionMeta}>{countLabel}</Text> : null}
    </Pressable>
  );
}
