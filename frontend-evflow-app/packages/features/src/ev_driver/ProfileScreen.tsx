import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { useNavigate } from 'react-router';
import {
  clearAuthSession,
  fetchEvModels,
  getAuthSession,
  getMe,
  saveAuthSession,
  updateProfile,
  type EVModelApiItem,
  type UserPublic
} from '@evflow/shared';
import { colors, fontSizes } from '@evflow/ui';

type ProfileScreenProps = {
  topInset?: number;
  bottomOffset?: number;
};

const CONNECTOR_OPTIONS = ['CCS2', 'CHAdeMO', 'Type 2', 'GB/T', 'Type 1'];

function initialsOf(user: UserPublic | null): string {
  const source = (user?.full_name || user?.username || user?.email || '?').trim();
  const parts = source.split(/\s+/).filter(Boolean);
  const letters = parts.length >= 2 ? parts[0][0] + parts[1][0] : source.slice(0, 2);
  return letters.toUpperCase();
}

function memberSince(iso?: string): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}

export function ProfileScreen({ topInset = 0, bottomOffset = 0 }: ProfileScreenProps) {
  const navigate = useNavigate();
  const sessionUser = getAuthSession()?.user ?? null;

  const [user, setUser] = useState<UserPublic | null>(sessionUser);
  const [loading, setLoading] = useState(true);
  const [models, setModels] = useState<EVModelApiItem[]>([]);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);

  const [username, setUsername] = useState(sessionUser?.username ?? '');
  const [evModelId, setEvModelId] = useState<string | null>(sessionUser?.ev_model_id ?? null);
  const [connector, setConnector] = useState<string | null>(sessionUser?.main_connector_type ?? null);
  const [locationConsent, setLocationConsent] = useState<boolean>(sessionUser?.location_consent ?? false);

  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const applyUser = (u: UserPublic) => {
    setUser(u);
    setUsername(u.username ?? '');
    setEvModelId(u.ev_model_id ?? null);
    setConnector(u.main_connector_type ?? null);
    setLocationConsent(u.location_consent ?? false);
  };

  useEffect(() => {
    let alive = true;
    getMe()
      .then((u) => { if (alive) applyUser(u); })
      .catch((err) => { if (alive && !sessionUser) setError(err instanceof Error ? err.message : 'Could not load your profile.'); })
      .finally(() => { if (alive) setLoading(false); });
    fetchEvModels({ limit: 300 })
      .then((res) => { if (alive) setModels(res.items); })
      .catch(() => { /* picker just stays empty */ });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedModel = useMemo(
    () => models.find((m) => m.id === evModelId) ?? null,
    [models, evModelId]
  );

  const dirty = Boolean(
    user &&
    (username.trim() !== (user.username ?? '') ||
      evModelId !== (user.ev_model_id ?? null) ||
      connector !== (user.main_connector_type ?? null) ||
      locationConsent !== user.location_consent)
  );

  const handleSave = () => {
    if (!dirty || saving) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    updateProfile({
      username: username.trim() || undefined,
      ev_model_id: evModelId,
      main_connector_type: connector,
      location_consent: locationConsent
    })
      .then((updated) => {
        applyUser(updated);
        const session = getAuthSession();
        if (session) saveAuthSession({ ...session, user: updated });
        setMessage('Your profile has been updated.');
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not save your changes.'))
      .finally(() => setSaving(false));
  };

  const handleLogout = () => {
    clearAuthSession();
    navigate('/');
  };

  return (
    <ScrollView
      contentContainerStyle={[styles.page, { paddingTop: 20 + topInset, paddingBottom: 24 + bottomOffset }]}
      keyboardShouldPersistTaps="handled"
    >
      <Text style={styles.heading}>Profile</Text>

      <View style={styles.identityCard}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initialsOf(user)}</Text>
        </View>
        <View style={styles.identityBody}>
          <Text style={styles.identityName} numberOfLines={1}>
            {user?.full_name || user?.username || 'EV Driver'}
          </Text>
          {user?.email ? <Text style={styles.identityEmail} numberOfLines={1}>{user.email}</Text> : null}
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{(user?.account_type ?? 'ev_user').replace(/_/g, ' ')}</Text>
          </View>
        </View>
      </View>

      {loading ? (
        <View style={styles.loadingRow}>
          <ActivityIndicator color={colors.text} />
          <Text style={styles.loadingText}>Loading your profile…</Text>
        </View>
      ) : null}

      <Text style={styles.sectionLabel}>Account</Text>
      <View style={styles.card}>
        <View style={styles.field}>
          <Text style={styles.fieldLabel}>Username</Text>
          <TextInput
            accessibilityLabel="Username"
            autoCapitalize="none"
            onChangeText={(value) => { setUsername(value); setMessage(null); setError(null); }}
            placeholder="Your username"
            placeholderTextColor="#8a969b"
            style={styles.input}
            value={username}
          />
        </View>
        <View style={styles.divider} />
        <View style={styles.readonlyRow}>
          <Text style={styles.fieldLabel}>Email</Text>
          <Text style={styles.readonlyValue}>{user?.email || 'Not set'}</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.readonlyRow}>
          <Text style={styles.fieldLabel}>Member since</Text>
          <Text style={styles.readonlyValue}>{memberSince(user?.created_at)}</Text>
        </View>
      </View>

      <Text style={styles.sectionLabel}>Vehicle</Text>
      <View style={styles.card}>
        <Text style={styles.fieldLabel}>EV model</Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => setModelPickerOpen((open) => !open)}
          style={styles.selectRow}
        >
          <Text style={[styles.selectValue, !selectedModel && styles.selectPlaceholder]}>
            {selectedModel ? selectedModel.name : (evModelId ?? 'Select your EV model')}
          </Text>
          <Text style={styles.chevron}>{modelPickerOpen ? '▲' : '▼'}</Text>
        </Pressable>

        {modelPickerOpen ? (
          <View style={styles.picker}>
            <Pressable
              onPress={() => { setEvModelId(null); setModelPickerOpen(false); }}
              style={styles.pickerItem}
            >
              <Text style={styles.pickerItemText}>None</Text>
            </Pressable>
            {models.map((model) => (
              <Pressable
                key={model.id}
                onPress={() => { setEvModelId(model.id); setModelPickerOpen(false); setMessage(null); }}
                style={[styles.pickerItem, model.id === evModelId && styles.pickerItemActive]}
              >
                <Text style={styles.pickerItemText} numberOfLines={1}>{model.name}</Text>
                {model.range_km ? <Text style={styles.pickerItemMeta}>{model.range_km} km</Text> : null}
              </Pressable>
            ))}
            {models.length === 0 ? <Text style={styles.pickerEmpty}>No models available.</Text> : null}
          </View>
        ) : null}

        <View style={styles.divider} />
        <Text style={styles.fieldLabel}>Main connector</Text>
        <View style={styles.pillRow}>
          {CONNECTOR_OPTIONS.map((option) => {
            const active = connector === option;
            return (
              <Pressable
                key={option}
                accessibilityRole="button"
                onPress={() => { setConnector(active ? null : option); setMessage(null); }}
                style={[styles.pill, active && styles.pillActive]}
              >
                <Text style={[styles.pillText, active && styles.pillTextActive]}>{option}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <Text style={styles.sectionLabel}>Preferences</Text>
      <View style={styles.card}>
        <View style={styles.switchRow}>
          <View style={styles.switchTextWrap}>
            <Text style={styles.switchTitle}>Share my location</Text>
            <Text style={styles.switchSub}>Used to show nearby charging stations and routing.</Text>
          </View>
          <Switch
            onValueChange={(value) => { setLocationConsent(value); setMessage(null); }}
            thumbColor={colors.white}
            trackColor={{ false: '#c4ced3', true: colors.primary }}
            value={locationConsent}
          />
        </View>
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}
      {message ? <Text style={styles.success}>{message}</Text> : null}

      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled: !dirty || saving }}
        disabled={!dirty || saving}
        onPress={handleSave}
        style={[styles.saveButton, (!dirty || saving) && styles.saveButtonDisabled]}
      >
        <Text style={styles.saveButtonText}>{saving ? 'Saving…' : 'Save Changes'}</Text>
      </Pressable>

      <Pressable accessibilityRole="button" onPress={handleLogout} style={styles.logoutButton}>
        <Text style={styles.logoutButtonText}>Log Out</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: {
    backgroundColor: colors.background,
    paddingHorizontal: 20,
    gap: 4
  },
  heading: {
    color: colors.text,
    fontSize: fontSizes.display,
    fontWeight: '800',
    marginBottom: 16
  },
  identityCard: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 16,
    padding: 16
  },
  avatar: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 28,
    height: 56,
    justifyContent: 'center',
    width: 56
  },
  avatarText: {
    color: colors.text,
    fontSize: fontSizes.titleSmall,
    fontWeight: '800'
  },
  identityBody: {
    flex: 1,
    gap: 3
  },
  identityName: {
    color: colors.text,
    fontSize: fontSizes.heading,
    fontWeight: '700'
  },
  identityEmail: {
    color: colors.mutedText,
    fontSize: fontSizes.caption
  },
  badge: {
    alignSelf: 'flex-start',
    backgroundColor: '#e3f8fa',
    borderRadius: 999,
    marginTop: 4,
    paddingHorizontal: 10,
    paddingVertical: 3
  },
  badgeText: {
    color: colors.text,
    fontSize: fontSizes.tiny,
    fontWeight: '700',
    textTransform: 'capitalize'
  },
  loadingRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    paddingTop: 12
  },
  loadingText: {
    color: colors.mutedText,
    fontSize: fontSizes.caption
  },
  sectionLabel: {
    color: colors.mutedText,
    fontSize: fontSizes.label,
    fontWeight: '700',
    marginBottom: 8,
    marginTop: 20,
    textTransform: 'uppercase'
  },
  card: {
    backgroundColor: colors.white,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    padding: 16
  },
  field: {
    gap: 6
  },
  fieldLabel: {
    color: colors.text,
    fontSize: fontSizes.label,
    fontWeight: '600'
  },
  input: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: 10,
    borderWidth: 1,
    color: colors.text,
    fontSize: fontSizes.body,
    marginTop: 6,
    paddingHorizontal: 12,
    paddingVertical: 10
  },
  divider: {
    backgroundColor: colors.border,
    height: 1,
    marginVertical: 14
  },
  readonlyRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between'
  },
  readonlyValue: {
    color: colors.mutedText,
    fontSize: fontSizes.body,
    maxWidth: '60%',
    textAlign: 'right'
  },
  selectRow: {
    alignItems: 'center',
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: 10,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 6,
    paddingHorizontal: 12,
    paddingVertical: 12
  },
  selectValue: {
    color: colors.text,
    fontSize: fontSizes.body,
    flex: 1
  },
  selectPlaceholder: {
    color: '#8a969b'
  },
  chevron: {
    color: colors.mutedText,
    fontSize: fontSizes.tiny,
    marginLeft: 8
  },
  picker: {
    borderColor: colors.border,
    borderRadius: 10,
    borderWidth: 1,
    marginTop: 8,
    maxHeight: 240,
    overflow: 'hidden'
  },
  pickerItem: {
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 11
  },
  pickerItemActive: {
    backgroundColor: '#e3f8fa'
  },
  pickerItemText: {
    color: colors.text,
    fontSize: fontSizes.control,
    flex: 1
  },
  pickerItemMeta: {
    color: colors.mutedText,
    fontSize: fontSizes.tiny,
    marginLeft: 8
  },
  pickerEmpty: {
    color: colors.mutedText,
    fontSize: fontSizes.caption,
    padding: 12
  },
  pillRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 8
  },
  pill: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 8
  },
  pillActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary
  },
  pillText: {
    color: colors.mutedText,
    fontSize: fontSizes.control,
    fontWeight: '600'
  },
  pillTextActive: {
    color: colors.text
  },
  switchRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between'
  },
  switchTextWrap: {
    flex: 1,
    paddingRight: 12
  },
  switchTitle: {
    color: colors.text,
    fontSize: fontSizes.body,
    fontWeight: '600'
  },
  switchSub: {
    color: colors.mutedText,
    fontSize: fontSizes.caption,
    marginTop: 2
  },
  error: {
    color: '#b3261e',
    fontSize: fontSizes.caption,
    fontWeight: '600',
    marginTop: 16
  },
  success: {
    color: '#006c4f',
    fontSize: fontSizes.caption,
    fontWeight: '700',
    marginTop: 16
  },
  saveButton: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 12,
    justifyContent: 'center',
    marginTop: 20,
    minHeight: 50
  },
  saveButtonDisabled: {
    opacity: 0.5
  },
  saveButtonText: {
    color: colors.text,
    fontSize: fontSizes.bodyLarge,
    fontWeight: '800'
  },
  logoutButton: {
    alignItems: 'center',
    borderColor: '#e6b4b0',
    borderRadius: 12,
    borderWidth: 1,
    justifyContent: 'center',
    marginTop: 12,
    minHeight: 50
  },
  logoutButtonText: {
    color: '#b3261e',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '700'
  }
});
