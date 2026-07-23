import { useState } from 'react';
import { Image, Pressable, ScrollView, Text, TextInput, View, type ImageSourcePropType } from 'react-native';
import { isValidEmail, login, requestPasswordReset, saveAuthSession } from '@evflow/shared';
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
  const [forgotOpen, setForgotOpen] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [resetEmailError, setResetEmailError] = useState<string | null>(null);
  const [resetMessage, setResetMessage] = useState<string | null>(null);
  const [resetSubmitting, setResetSubmitting] = useState(false);
  const canSubmit = username.trim().length > 0 && password.length > 0 && !submitting;
  const canRequestReset = resetEmail.trim().length > 0 && !resetSubmitting;

  const handleLogin = () => {
    if (!canSubmit) {
      setError('Enter your username or email and password.');
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

  const handleForgotPassword = () => {
    setForgotOpen((current) => !current);
    setResetEmail(username.includes('@') ? username.trim() : resetEmail);
    setResetEmailError(null);
    setResetMessage(null);
  };

  const handleRequestReset = () => {
    const email = resetEmail.trim();

    if (!email) {
      setResetEmailError('Email is required.');
      return;
    }

    if (!isValidEmail(email)) {
      setResetEmailError('Enter a valid email address.');
      return;
    }

    if (resetSubmitting) {
      return;
    }

    setResetSubmitting(true);
    setResetEmailError(null);
    setResetMessage(null);

    requestPasswordReset({ email })
      .then((response) => {
        setResetMessage(response.message || 'Password reset instructions have been sent to your email.');
      })
      .catch((err) => {
        setResetEmailError(err instanceof Error ? err.message : 'Could not send reset instructions. Please try again.');
      })
      .finally(() => setResetSubmitting(false));
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
          <Text style={styles.inputLabel}>Username or Email</Text>
          <TextInput
            accessibilityLabel="Username or email"
            autoCapitalize="none"
            keyboardType="default"
            onChangeText={(value) => {
              setUsername(value);
              setError(null);
            }}
            placeholder="Enter your username or email"
            placeholderTextColor="#7c858b"
            style={styles.input}
            value={username}
          />
        </View>

        <View style={styles.fieldGroup}>
          <View style={styles.passwordLabelRow}>
            <Text style={styles.inputLabel}>Password</Text>
            <Text onPress={handleForgotPassword} style={styles.forgotText}>Forgot?</Text>
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

        {forgotOpen ? (
          <View style={styles.fieldGroup}>
            <Text style={styles.inputLabel}>Reset password email</Text>
            <TextInput
              accessibilityLabel="Reset password email"
              autoCapitalize="none"
              keyboardType="email-address"
              onChangeText={(value) => {
                setResetEmail(value);
                setResetEmailError(null);
                setResetMessage(null);
              }}
              onSubmitEditing={handleRequestReset}
              placeholder="name@example.com"
              placeholderTextColor="#7c858b"
              style={styles.input}
              value={resetEmail}
            />
            {resetEmailError ? <Text style={styles.errorText}>{resetEmailError}</Text> : null}
            {resetMessage ? <Text style={{ color: '#006c4f', fontSize: 12, fontWeight: '700', lineHeight: 18 }}>{resetMessage}</Text> : null}
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: !canRequestReset }}
              disabled={!canRequestReset}
              onPress={handleRequestReset}
              style={[styles.loginButton, { marginTop: 8, minHeight: 44 }, !canRequestReset && styles.disabledButton]}
            >
              <Text style={styles.loginButtonText}>{resetSubmitting ? 'Sending...' : 'Send Reset Email'}</Text>
            </Pressable>
          </View>
        ) : null}

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
