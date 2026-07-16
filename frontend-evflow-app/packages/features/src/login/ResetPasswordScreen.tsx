import { useMemo, useState } from 'react';
import { Image, Pressable, ScrollView, Text, TextInput, View, type ImageSourcePropType } from 'react-native';
import { resetPassword } from '@evflow/shared';
import { loginScreenStyles as styles } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import evflowIcon from '../assets/images/evflow-icon.png';

const evflowIconSource = evflowIcon as unknown as ImageSourcePropType;

type ResetPasswordScreenProps = {
  token: string | null;
  onBackToLogin: () => void;
};

export function ResetPasswordScreen({ token, onBackToLogin }: ResetPasswordScreenProps) {
  const insets = useAppSafeAreaInsets();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const canSubmit = useMemo(
    () => Boolean(token) && password.length >= 8 && confirm.length >= 8 && !submitting,
    [token, password, confirm, submitting]
  );

  const handleSubmit = () => {
    if (!token) {
      setError('This reset link is missing its token. Request a new one from the login screen.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    if (submitting) {
      return;
    }

    setSubmitting(true);
    setError(null);

    resetPassword({ token, new_password: password })
      .then(() => {
        setDone(true);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Could not reset your password. Please try again.');
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
        <Text style={styles.appSubtitle}>Reset your password</Text>

        {done ? (
          <>
            <Text style={{ color: '#006c4f', fontSize: 14, fontWeight: '700', lineHeight: 20, marginTop: 12 }}>
              Your password has been reset. You can now log in with your new password.
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={onBackToLogin}
              style={[styles.loginButton, { marginTop: 16 }]}
            >
              <Text style={styles.loginButtonText}>Back to Log In</Text>
            </Pressable>
          </>
        ) : !token ? (
          <>
            <Text style={styles.errorText}>
              This reset link is invalid or incomplete. Request a new one from the login screen.
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={onBackToLogin}
              style={[styles.loginButton, { marginTop: 16 }]}
            >
              <Text style={styles.loginButtonText}>Back to Log In</Text>
            </Pressable>
          </>
        ) : (
          <>
            <View style={styles.fieldGroup}>
              <Text style={styles.inputLabel}>New Password</Text>
              <TextInput
                accessibilityLabel="New password"
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

            <View style={styles.fieldGroup}>
              <Text style={styles.inputLabel}>Confirm New Password</Text>
              <TextInput
                accessibilityLabel="Confirm new password"
                onChangeText={(value) => {
                  setConfirm(value);
                  setError(null);
                }}
                onSubmitEditing={handleSubmit}
                placeholder="Re-enter your new password"
                placeholderTextColor="#69777c"
                secureTextEntry
                style={styles.input}
                value={confirm}
              />
            </View>

            {error ? <Text style={styles.errorText}>{error}</Text> : null}

            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: !canSubmit }}
              disabled={!canSubmit}
              onPress={handleSubmit}
              style={[styles.loginButton, !canSubmit && styles.disabledButton]}
            >
              <Text style={styles.loginButtonText}>{submitting ? 'Resetting...' : 'Reset Password'}</Text>
            </Pressable>

            <View style={styles.signupSeparator} />

            <Text style={styles.signupText}>
              Remembered your password?{' '}
              <Text onPress={onBackToLogin} style={styles.signupLink}>
                Back to Log In
              </Text>
            </Text>
          </>
        )}
      </View>

      <View style={styles.spacer} />
    </ScrollView>
  );
}
