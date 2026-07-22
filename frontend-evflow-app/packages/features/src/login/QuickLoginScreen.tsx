import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, View } from 'react-native';
import { useNavigate } from 'react-router';
import { AuthApiError } from '@evflow/shared';
import { colors, quickLoginStyles as styles } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';
import { demoPersonas, ensureDemoSession, type DemoPersona, type DemoPersonaKey } from './demoPersonas';

const NETWORK_ERROR_MESSAGE = 'Cannot reach the server. Please try again.';
const CREDENTIAL_DRIFT_MESSAGE = 'This demo profile is unavailable right now. Please try again later.';

function getQuickLoginErrorMessage(error: unknown): string {
  if (!(error instanceof AuthApiError)) {
    return NETWORK_ERROR_MESSAGE;
  }

  if (error.status === 401 || error.status === 409) {
    return CREDENTIAL_DRIFT_MESSAGE;
  }

  // The server was reached but rejected the request; its message is more useful
  // than a generic connectivity hint.
  return error.message || NETWORK_ERROR_MESSAGE;
}

export function QuickLoginScreen() {
  const navigate = useNavigate();
  const insets = useAppSafeAreaInsets();
  const [pendingKey, setPendingKey] = useState<DemoPersonaKey | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSelect = (persona: DemoPersona) => {
    if (pendingKey) {
      return;
    }

    setPendingKey(persona.key);
    setError(null);

    ensureDemoSession(persona)
      .then(() => {
        navigate(persona.key === 'driver' ? '/onboarding/vehicle' : '/business/dashboard');
      })
      .catch((err: unknown) => {
        console.error('Quick login failed', err);
        setError(getQuickLoginErrorMessage(err));
        setPendingKey(null);
      });
  };

  return (
    <ScrollView contentContainerStyle={[styles.page, { paddingBottom: 36 + insets.bottom }]}>
      <View style={styles.contentShell}>
        <View style={[styles.brandHeader, { paddingTop: 56 + insets.top }]}>
          <View style={styles.logoCircle}>
            <SvgAssetIcon color={colors.white} height={30} name="lightning" width={26} />
          </View>
          <Text style={styles.appTitle}>EV-FLOW</Text>
          <Text style={styles.tagline}>Electric Vehicle Forecasting & Location Optimization</Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.welcomeTitle}>Welcome back</Text>
          <Text style={styles.welcomeSubtitle}>Tap a profile to continue — no password needed</Text>

          <View style={styles.cardList}>
            {demoPersonas.map((persona) => (
              <PersonaCard
                disabled={pendingKey !== null}
                key={persona.key}
                pending={pendingKey === persona.key}
                persona={persona}
                onPress={() => handleSelect(persona)}
              />
            ))}
          </View>

          {error ? <Text style={styles.errorText}>{error}</Text> : null}
        </View>
      </View>
    </ScrollView>
  );
}

type PersonaCardProps = {
  persona: DemoPersona;
  pending: boolean;
  disabled: boolean;
  onPress: () => void;
};

function PersonaCard({ persona, pending, disabled, onPress }: PersonaCardProps) {
  return (
    <Pressable
      accessibilityLabel={`Continue as ${persona.fullName}`}
      accessibilityRole="button"
      accessibilityState={{ busy: pending, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.personaCard, disabled && !pending && styles.personaCardDisabled]}
    >
      <View style={[styles.avatar, { backgroundColor: persona.avatarColor }]}>
        <Text style={styles.avatarText}>{persona.initials}</Text>
      </View>

      <View style={styles.personaBody}>
        <Text style={styles.personaName}>{persona.fullName}</Text>
        <Text style={[styles.personaSubtitle, { color: persona.subtitleColor }]}>{persona.subtitle}</Text>
      </View>

      {pending ? <ActivityIndicator color={colors.text} size="small" /> : <Text style={styles.chevron}>›</Text>}
    </Pressable>
  );
}
