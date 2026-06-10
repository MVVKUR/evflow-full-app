import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { fetchConnectorTypes, fetchEvModels, register, saveAuthSession, type ConnectorTypeApiItem, type EVModelApiItem } from '@evflow/shared';
import { registrationScreenStyles as styles } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';
import { PlatformSlider } from '../shared/PlatformSlider';
import { ModelPicker } from './components/ModelPicker';

type RegistrationScreenProps = {
  onBack: () => void;
  onLogin: () => void;
  onRegister: () => void;
};

const batteryThresholds = [10, 15, 20, 25, 30, 35, 40] as const;
const defaultConnectorTypes: ConnectorTypeApiItem[] = [
  { name: 'CCS2', count: 0 },
  { name: 'AC Type 2', count: 0 }
];

export function RegistrationScreen({ onBack, onLogin, onRegister }: RegistrationScreenProps) {
  const insets = useAppSafeAreaInsets();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [selectedCarId, setSelectedCarId] = useState('');
  const [selectedConnectorType, setSelectedConnectorType] = useState('');
  const [batteryThreshold, setBatteryThreshold] = useState(20);
  const [permissionGranted, setPermissionGranted] = useState(true);
  const [evModels, setEvModels] = useState<EVModelApiItem[]>([]);
  const [evModelsError, setEvModelsError] = useState<string | null>(null);
  const [connectorTypes, setConnectorTypes] = useState<ConnectorTypeApiItem[]>([]);
  const [connectorTypesLoading, setConnectorTypesLoading] = useState(true);
  const [connectorTypesError, setConnectorTypesError] = useState<string | null>(null);
  const [usingDefaultConnectorTypes, setUsingDefaultConnectorTypes] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function loadEvModels() {
      try {
        const response = await fetchEvModels({ limit: 500 });

        if (mounted) {
          setEvModels(response.items);
        }
      } catch (error) {
        if (mounted) {
          setEvModelsError(error instanceof Error ? error.message : 'Unable to load EV models.');
        }
      }
    }

    loadEvModels();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadConnectorTypes() {
      setConnectorTypesLoading(true);
      setConnectorTypesError(null);

      try {
        const response = await fetchConnectorTypes();
        const options = response.length > 0 ? response : defaultConnectorTypes;

        if (mounted) {
          setConnectorTypes(options);
          setUsingDefaultConnectorTypes(response.length === 0);
          setSelectedConnectorType((current) => {
            if (options.some((connectorType) => connectorType.name === current)) {
              return current;
            }

            return options[0]?.name ?? '';
          });
        }
      } catch (error) {
        if (mounted) {
          setConnectorTypesError(error instanceof Error ? error.message : 'Unable to load connector types.');
          setConnectorTypes(defaultConnectorTypes);
          setUsingDefaultConnectorTypes(true);
          setSelectedConnectorType((current) => {
            if (defaultConnectorTypes.some((connectorType) => connectorType.name === current)) {
              return current;
            }

            return defaultConnectorTypes[0]?.name ?? '';
          });
        }
      } finally {
        if (mounted) {
          setConnectorTypesLoading(false);
        }
      }
    }

    loadConnectorTypes();

    return () => {
      mounted = false;
    };
  }, []);

  const selectedCar = useMemo(
    () => evModels.find((model) => model.id === selectedCarId),
    [evModels, selectedCarId]
  );
  const evModelOptions = useMemo(
    () =>
      evModels.map((model) => ({
        label: `${model.name} (${[model.battery_kwh ? `${model.battery_kwh} kWh` : null, model.range_km ? `${model.range_km} km` : null].filter(Boolean).join(' - ')})`,
        value: model.id
      })),
    [evModels]
  );
  const selectedBatteryIndex = batteryThresholds.findIndex((threshold) => threshold === batteryThreshold);
  const batteryPercent = (selectedBatteryIndex / (batteryThresholds.length - 1)) * 100;
  const canRegister =
    username.trim().length >= 3 &&
    password.length >= 8 &&
    Boolean(selectedCarId) &&
    Boolean(selectedConnectorType) &&
    !submitting;

  const handleRegister = () => {
    if (!canRegister) {
      setSubmitError('Complete all fields. Password must be at least 8 characters.');
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    register({
      ev_model_id: selectedCarId,
      location_consent: permissionGranted,
      main_connector_type: selectedConnectorType,
      password,
      username: username.trim()
    })
      .then((session) => {
        saveAuthSession(session);
        onRegister();
      })
      .catch((error) => {
        setSubmitError(error instanceof Error ? error.message : 'Unable to register. Please try again.');
      })
      .finally(() => setSubmitting(false));
  };

  return (
    <View style={styles.page}>
      <View style={[styles.header, { paddingTop: insets.top }]}>
        <Pressable accessibilityLabel="Back" accessibilityRole="button" onPress={onBack} style={styles.backButton}>
          <SvgAssetIcon color="#191C1D" height={12} name="leftChevron" width={8} />
          <Text style={styles.backText}>Back</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: 28 + insets.bottom }]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.title}>Create New Account</Text>
        <Text style={styles.subtitle}>Join for access to EV-FLOW smart routing.</Text>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Username</Text>
          <TextInput
            accessibilityLabel="Username"
            autoCapitalize="none"
            onChangeText={(value) => {
              setUsername(value);
              setSubmitError(null);
            }}
            placeholder="Enter your username"
            placeholderTextColor="#9aa4a9"
            style={styles.input}
            value={username}
          />
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Password</Text>
          <TextInput
            accessibilityLabel="Password"
            autoCapitalize="none"
            onChangeText={(value) => {
              setPassword(value);
              setSubmitError(null);
            }}
            placeholder="Enter your password"
            placeholderTextColor="#9aa4a9"
            secureTextEntry
            style={styles.input}
            value={password}
          />
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Car Brand & Model</Text>
          <View style={styles.select}>
            <ModelPicker
              selectedValue={selectedCarId}
              onValueChange={(value) => {
                setSelectedCarId(value);
                setSubmitError(null);
              }}
              options={evModelOptions}
              placeholderLabel={evModelsError ? 'EV models unavailable' : 'Select your car'}
            />
          </View>
        </View>

        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Main Connector Type</Text>
          <View style={styles.connectorRow}>
            {connectorTypes.map((connectorType) => {
              const selected = connectorType.name === selectedConnectorType;

              return (
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  key={connectorType.name}
                  onPress={() => {
                    setSelectedConnectorType(connectorType.name);
                    setSubmitError(null);
                  }}
                  style={[styles.connectorPill, selected && styles.selectedConnectorPill]}
                >
                  <Text style={[styles.connectorText, selected && styles.selectedConnectorText]}>{connectorType.name}</Text>
                </Pressable>
              );
            })}
          </View>
          {connectorTypesLoading ? <Text style={styles.helperText}>Loading connector types...</Text> : null}
          {!connectorTypesLoading && usingDefaultConnectorTypes ? <Text style={styles.helperText}>Using default connector types.</Text> : null}
          {connectorTypesError && !usingDefaultConnectorTypes ? <Text style={styles.helperText}>Connector types unavailable.</Text> : null}
        </View>

        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: permissionGranted }}
          onPress={() => setPermissionGranted((current) => !current)}
          style={styles.permissionCard}
        >
          <View style={[styles.checkbox, permissionGranted && styles.checkedBox]}>
            {permissionGranted ? <Text style={styles.checkText}>✓</Text> : null}
          </View>
          <View style={styles.permissionTextWrap}>
            <Text style={styles.permissionTitle}>Access Permission & Periodic Location Recording</Text>
            <Text style={styles.permissionBody}>
              Your journey coordinate data will be recorded anonymously to support Charging Station demand mapping by the 4JKT team. We respect your privacy in accordance with data protection mandates.
            </Text>
          </View>
        </Pressable>

        {submitError ? <Text style={styles.errorText}>{submitError}</Text> : null}

        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: !canRegister }}
          disabled={!canRegister}
          onPress={handleRegister}
          style={[styles.registerButton, !canRegister && styles.disabledButton]}
        >
          <Text style={styles.registerButtonText}>{submitting ? 'Registering...' : 'Register'}</Text>
        </Pressable>

        <Text style={styles.loginPrompt}>
          Already have an account?{' '}
          <Text onPress={onLogin} style={styles.loginLink}>
            Log In
          </Text>
        </Text>

        <View style={styles.homeIndicator} />
        <Text style={styles.poweredBy}>POWERED BY EV-FLOW ECOSYSTEM</Text>
      </ScrollView>
    </View>
  );
}
