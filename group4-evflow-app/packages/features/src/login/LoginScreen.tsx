import { useState } from 'react';
import { Image, Pressable, ScrollView, Text, TextInput, View, type ImageSourcePropType } from 'react-native';
import { login, saveAuthSession } from '@evflow/shared';
import { loginScreenStyles as styles } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import evflowIcon from '../assets/images/evflow-icon.png';

const evflowIconSource = evflowIcon as unknown as ImageSourcePropType;

type LoginScreenProps = {
  onLogin: () => void;
  onRegister: () => void;
};

export function LoginScreen({ onLogin, onRegister }: LoginScreenProps) {
  const insets = useAppSafeAreaInsets();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canSubmit = username.trim().length > 0 && password.length > 0 && !submitting;

  const handleLogin = () => {
    if (!canSubmit) {
      setError('Enter your username and password.');
      return;
    }

    setSubmitting(true);
    setError(null);

    login({
      password,
      username: username.trim()
    })
      .then((session) => {
        saveAuthSession(session);
        onLogin();
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Unable to log in. Please try again.');
      })
      .finally(() => setSubmitting(false));
  };

  return (
    <ScrollView
      contentContainerStyle={[
        styles.page,
        {
          paddingBottom: 36 + insets.bottom,
          paddingTop: 36 + insets.top
        }
      ]}
      keyboardShouldPersistTaps="handled"
    >
      <View style={styles.spacer} />

      <View style={styles.content}>
        <View style={styles.logoWrap}>
          <Image source={evflowIconSource} style={styles.logoImage} />
        </View>

        <Text style={styles.appTitle}>EV-FLOW</Text>
        <Text style={styles.appSubtitle}>Electric Vehicle Forecasting & Location Optimization Wayfinder</Text>

        <View style={styles.fieldGroup}>
          <Text style={styles.inputLabel}>Username</Text>
          <TextInput
            accessibilityLabel="Username"
            autoCapitalize="none"
            keyboardType="default"
            onChangeText={(value) => {
              setUsername(value);
              setError(null);
            }}
            placeholder="Enter your username"
            placeholderTextColor="#7c858b"
            style={styles.input}
            value={username}
          />
        </View>

        <View style={styles.fieldGroup}>
          <View style={styles.passwordLabelRow}>
            <Text style={styles.inputLabel}>Password</Text>
            <Text style={styles.forgotText}>Forgot?</Text>
          </View>
          <TextInput
            accessibilityLabel="Password"
            onChangeText={(value) => {
              setPassword(value);
              setError(null);
            }}
            placeholder="Minimum 8 characters"
            placeholderTextColor="#69777c"
            secureTextEntry
            style={styles.input}
            value={password}
          />
        </View>

        {error ? <Text style={styles.errorText}>{error}</Text> : null}

        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: !canSubmit }}
          disabled={!canSubmit}
          onPress={handleLogin}
          style={[styles.loginButton, !canSubmit && styles.disabledButton]}
        >
          <Text style={styles.loginButtonText}>{submitting ? 'Logging In...' : 'Log In'}</Text>
        </Pressable>

        <View style={styles.signupSeparator} />

        <Text style={styles.signupText}>
          Don't have an account?{' '}
          <Text onPress={onRegister} style={styles.signupLink}>
            Register Now
          </Text>
        </Text>
      </View>

      <View style={styles.spacer} />
    </ScrollView>
  );
}
