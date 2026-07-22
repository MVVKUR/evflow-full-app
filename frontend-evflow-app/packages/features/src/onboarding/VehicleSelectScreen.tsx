import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, View } from 'react-native';
import { useNavigate } from 'react-router';
import { fetchEvModels, getMe, type EVModelApiItem } from '@evflow/shared';
import { colors, onboardingStyles as styles } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';

const OTHER_BRAND = 'Other';

type VehicleSelection = {
  evModelId: string | null;
};

function brandOf(model: EVModelApiItem): string {
  return model.make?.trim() || OTHER_BRAND;
}

function modelMeta(model: EVModelApiItem): string | null {
  const parts: string[] = [];

  if (model.battery_kwh !== null) {
    parts.push(`${model.battery_kwh} kWh`);
  }

  if (model.range_km !== null) {
    parts.push(`${model.range_km} km`);
  }

  return parts.length > 0 ? parts.join(' · ') : null;
}

export function VehicleSelectScreen() {
  const navigate = useNavigate();
  const insets = useAppSafeAreaInsets();
  const [models, setModels] = useState<EVModelApiItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [selectedBrand, setSelectedBrand] = useState<string | null>(null);
  const [selection, setSelection] = useState<VehicleSelection | null>(null);
  const [prefillModelId, setPrefillModelId] = useState<string | null>(null);

  // loadModels is triggered from both the mount effect and the Retry button,
  // so a mounted ref (rather than a per-effect flag) guards its state updates.
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadModels = useCallback(() => {
    setLoading(true);
    setLoadFailed(false);

    fetchEvModels({ limit: 200 })
      .then((response) => {
        if (!mountedRef.current) {
          return;
        }

        setModels(response.items);
        setLoadFailed(response.items.length === 0);
      })
      .catch((err: unknown) => {
        console.error('Failed to load EV models', err);

        if (mountedRef.current) {
          setLoadFailed(true);
        }
      })
      .finally(() => {
        if (mountedRef.current) {
          setLoading(false);
        }
      });
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  useEffect(() => {
    let alive = true;

    getMe()
      .then((user) => {
        if (alive && user.ev_model_id) {
          setPrefillModelId(user.ev_model_id);
        }
      })
      .catch(() => {
        // Prefill is best-effort only; the screen works without it.
      });

    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!prefillModelId || selection) {
      return;
    }

    const match = models.find((model) => model.id === prefillModelId);

    if (match) {
      setSelection({ evModelId: match.id });
      setSelectedBrand(brandOf(match));
    }
  }, [models, prefillModelId, selection]);

  const brands = useMemo(() => {
    const names = [...new Set(models.map(brandOf))];
    return names.sort((a, b) => a.localeCompare(b));
  }, [models]);

  const brandModels = useMemo(
    () => models.filter((model) => selectedBrand !== null && brandOf(model) === selectedBrand),
    [models, selectedBrand]
  );

  const canContinue = selection !== null;

  const handleContinue = () => {
    if (!selection) {
      return;
    }

    navigate('/onboarding/connector', { state: { evModelId: selection.evModelId } });
  };

  return (
    <View style={styles.page}>
      <View style={styles.contentShell}>
        <View style={[styles.header, { paddingTop: insets.top }]}>
          <Pressable accessibilityLabel="Back" accessibilityRole="button" onPress={() => navigate('/')} style={styles.backButton}>
            <SvgAssetIcon color="#191C1D" height={12} name="leftChevron" width={8} />
          </Pressable>
          <Text style={styles.brand}>EV-FLOW</Text>
          <View style={styles.headerSpacer} />
        </View>

        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: 140 + insets.bottom }]}>
          <Text style={styles.title}>What car do you drive?</Text>
          <Text style={styles.subtitle}>Pick your brand, then your model. This helps us match chargers to your car.</Text>

          {loading ? (
            <View style={styles.loadingRow}>
              <ActivityIndicator color={colors.text} size="small" />
            </View>
          ) : null}

          {!loading && loadFailed ? (
            <View style={styles.noticeBox}>
              <Text style={styles.noticeText}>Couldn't load the car list.</Text>
              <Pressable accessibilityRole="button" onPress={loadModels} style={styles.retryButton}>
                <Text style={styles.retryButtonText}>Retry</Text>
              </Pressable>
            </View>
          ) : null}

          {brands.length > 0 ? (
            <View style={styles.brandChipsRow}>
              {brands.map((brand) => (
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ selected: selectedBrand === brand }}
                  key={brand}
                  onPress={() => setSelectedBrand(brand)}
                  style={[styles.brandChip, selectedBrand === brand && styles.brandChipSelected]}
                >
                  <Text style={[styles.brandChipText, selectedBrand === brand && styles.brandChipTextSelected]}>
                    {brand}
                  </Text>
                </Pressable>
              ))}
            </View>
          ) : null}

          {brandModels.length > 0 ? (
            <View style={styles.optionList}>
              {brandModels.map((model) => (
                <ModelCard
                  key={model.id}
                  model={model}
                  selected={selection?.evModelId === model.id}
                  onPress={() => setSelection({ evModelId: model.id })}
                />
              ))}
            </View>
          ) : null}

          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: selection !== null && selection.evModelId === null }}
            onPress={() => setSelection({ evModelId: null })}
            style={[
              styles.optionCard,
              styles.fallbackCard,
              selection !== null && selection.evModelId === null && styles.optionCardSelected
            ]}
          >
            <Text style={styles.optionName}>My car isn't listed</Text>
            <Text style={styles.optionMeta}>
              Continue and pick your plug type manually — you can set the car later in Profile.
            </Text>
          </Pressable>
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: 20 + insets.bottom }]}>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: !canContinue }}
            disabled={!canContinue}
            onPress={handleContinue}
            style={[styles.continueButton, !canContinue && styles.disabledButton]}
          >
            <Text style={styles.continueText}>Continue</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

type ModelCardProps = {
  model: EVModelApiItem;
  selected: boolean;
  onPress: () => void;
};

function ModelCard({ model, selected, onPress }: ModelCardProps) {
  const meta = modelMeta(model);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.optionCard, selected && styles.optionCardSelected]}
    >
      <Text style={styles.optionName}>{model.name}</Text>
      {meta ? <Text style={styles.optionMeta}>{meta}</Text> : null}
    </Pressable>
  );
}
