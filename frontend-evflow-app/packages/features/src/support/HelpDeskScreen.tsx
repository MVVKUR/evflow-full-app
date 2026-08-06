import { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { getAuthSession } from '@evflow/shared';
import { colors, fontSizes } from '@evflow/ui';
// Deep relative import: the "@evflow/shared" barrel (packages/shared/src/index.ts)
// does not re-export ./support/api and is owned by another agent this run.
import {
  submitSupportTicket,
  toSupportFailureKind,
  toSupportRetryAfterSeconds
} from '../../../shared/src/support/api';
import {
  buildSupportTicketRequest,
  EMPTY_SUPPORT_FORM,
  hasSupportFormErrors,
  remainingCharacters,
  SUPPORT_EMAIL_MAX_LENGTH,
  SUPPORT_MESSAGE_MAX_LENGTH,
  SUPPORT_SUBJECT_MAX_LENGTH,
  validateSupportForm,
  type SupportFormValues
} from './supportValidation';
import { describeSupportFailure, describeSupportSuccess, SUPPORT_INVALID_FORM_MESSAGE } from './supportMessages';

type HelpDeskScreenProps = {
  bottomOffset?: number;
  topInset?: number;
  onBack: () => void;
};

export function HelpDeskScreen({ bottomOffset = 0, topInset = 0, onBack }: HelpDeskScreenProps) {
  // Prefilled, not implied: the API sends "Reply-to: not supplied" when this is
  // blank, so an unanswerable ticket is a real outcome we have to design against.
  const [initialForm] = useState<SupportFormValues>(() => ({
    ...EMPTY_SUPPORT_FORM,
    replyToEmail: getAuthSession()?.user?.email ?? ''
  }));
  const [values, setValues] = useState<SupportFormValues>(initialForm);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [sentReplyTo, setSentReplyTo] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const errors = useMemo(() => validateSupportForm(values), [values]);

  const updateField = (field: keyof SupportFormValues) => (value: string) => {
    setValues((current) => ({ ...current, [field]: value }));
    setSubmitError(null);
  };

  const handleSubmit = () => {
    setSubmitAttempted(true);

    if (hasSupportFormErrors(errors)) {
      setSubmitError(SUPPORT_INVALID_FORM_MESSAGE);
      return;
    }

    if (submitting) {
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    const request = buildSupportTicketRequest(values);

    submitSupportTicket(request)
      .then(() => {
        setSentReplyTo(request.reply_to ?? null);
        setSent(true);
        setValues(initialForm);
        setSubmitAttempted(false);
      })
      .catch((error: unknown) => {
        // Only the classified kind reaches the UI; the server's body never does.
        setSubmitError(describeSupportFailure(toSupportFailureKind(error), toSupportRetryAfterSeconds(error)));
      })
      .finally(() => setSubmitting(false));
  };

  if (sent) {
    return (
      <SupportSentScreen
        bottomOffset={bottomOffset}
        replyTo={sentReplyTo}
        topInset={topInset}
        onBack={onBack}
        onSendAnother={() => setSent(false)}
      />
    );
  }

  const showError = (field: keyof SupportFormValues) =>
    (submitAttempted || values[field].length > 0) && errors[field] ? errors[field] : null;

  return (
    <ScrollView
      contentContainerStyle={[styles.page, { paddingTop: 20 + topInset, paddingBottom: 24 + bottomOffset }]}
      keyboardShouldPersistTaps="handled"
    >
      <Pressable accessibilityLabel="Back to profile" accessibilityRole="button" onPress={onBack} style={styles.backButton}>
        <Text style={styles.backChevron}>‹</Text>
        <Text style={styles.backText}>Profile</Text>
      </Pressable>

      <Text style={styles.heading}>Help Desk</Text>
      <Text style={styles.intro}>
        Tell us what went wrong and the EV-FLOW support team will get back to you by email.
      </Text>

      <Text style={styles.sectionLabel}>Your message</Text>
      <View style={styles.card}>
        <View style={styles.field}>
          <Text style={styles.fieldLabel}>Subject</Text>
          <TextInput
            accessibilityLabel="Subject"
            editable={!submitting}
            maxLength={SUPPORT_SUBJECT_MAX_LENGTH}
            onChangeText={updateField('subject')}
            placeholder="Charging session was not stopped"
            placeholderTextColor="#8a969b"
            style={styles.input}
            value={values.subject}
          />
          {showError('subject') ? <Text style={styles.errorText}>{errors.subject}</Text> : null}
        </View>

        <View style={styles.divider} />

        <View style={styles.field}>
          <View style={styles.fieldHeaderRow}>
            <Text style={styles.fieldLabel}>Message</Text>
            <Text style={styles.counter}>{remainingCharacters(values.message, SUPPORT_MESSAGE_MAX_LENGTH)} left</Text>
          </View>
          <TextInput
            accessibilityLabel="Message"
            editable={!submitting}
            maxLength={SUPPORT_MESSAGE_MAX_LENGTH}
            multiline
            numberOfLines={6}
            onChangeText={updateField('message')}
            placeholder="Describe what happened, which station you were at, and when."
            placeholderTextColor="#8a969b"
            style={[styles.input, styles.textArea]}
            textAlignVertical="top"
            value={values.message}
          />
          {showError('message') ? <Text style={styles.errorText}>{errors.message}</Text> : null}
        </View>

        <View style={styles.divider} />

        <View style={styles.field}>
          <Text style={styles.fieldLabel}>Reply-to email (optional)</Text>
          <TextInput
            accessibilityLabel="Reply-to email"
            autoCapitalize="none"
            editable={!submitting}
            keyboardType="email-address"
            maxLength={SUPPORT_EMAIL_MAX_LENGTH}
            onChangeText={updateField('replyToEmail')}
            placeholder="you@example.com"
            placeholderTextColor="#8a969b"
            style={styles.input}
            value={values.replyToEmail}
          />
          {showError('replyToEmail') ? (
            <Text style={styles.errorText}>{errors.replyToEmail}</Text>
          ) : (
            <Text style={styles.helperText}>Support replies to this address. Without it your ticket cannot be answered.</Text>
          )}
        </View>
      </View>

      {submitError ? <Text style={styles.error}>{submitError}</Text> : null}

      {/* Disabled only in flight, not while the form is invalid. Greying it out
          on an invalid form -- the pattern on RegistrationScreen -- leaves a
          driver who has not touched a required field with a dead button and no
          error next to it. Pressing here reveals every error instead. */}
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ busy: submitting, disabled: submitting }}
        disabled={submitting}
        onPress={handleSubmit}
        style={[styles.submitButton, submitting && styles.submitButtonDisabled]}
      >
        {submitting ? <ActivityIndicator color={colors.text} /> : null}
        <Text style={styles.submitButtonText}>{submitting ? 'Sending…' : 'Send Message'}</Text>
      </Pressable>
    </ScrollView>
  );
}

type SupportSentScreenProps = {
  bottomOffset: number;
  replyTo: string | null;
  topInset: number;
  onBack: () => void;
  onSendAnother: () => void;
};

function SupportSentScreen({ bottomOffset, replyTo, topInset, onBack, onSendAnother }: SupportSentScreenProps) {
  return (
    <ScrollView contentContainerStyle={[styles.page, { paddingTop: 20 + topInset, paddingBottom: 24 + bottomOffset }]}>
      <Pressable accessibilityLabel="Back to profile" accessibilityRole="button" onPress={onBack} style={styles.backButton}>
        <Text style={styles.backChevron}>‹</Text>
        <Text style={styles.backText}>Profile</Text>
      </Pressable>

      <Text style={styles.heading}>Help Desk</Text>

      <View style={styles.card}>
        <View style={styles.sentMark}>
          <Text style={styles.sentCheck}>✓</Text>
        </View>
        <Text style={styles.sentTitle}>Message sent</Text>
        <Text style={styles.sentBody}>{describeSupportSuccess(replyTo)}</Text>
      </View>

      <Pressable accessibilityRole="button" onPress={onSendAnother} style={styles.submitButton}>
        <Text style={styles.submitButtonText}>Send Another Message</Text>
      </Pressable>

      <Pressable accessibilityRole="button" onPress={onBack} style={styles.secondaryButton}>
        <Text style={styles.secondaryButtonText}>Back to Profile</Text>
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
  backButton: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    flexDirection: 'row',
    gap: 6,
    marginBottom: 8,
    paddingVertical: 6
  },
  backChevron: {
    color: colors.text,
    fontSize: fontSizes.heading,
    fontWeight: '800'
  },
  backText: {
    color: colors.text,
    fontSize: fontSizes.control,
    fontWeight: '700'
  },
  heading: {
    color: colors.text,
    fontSize: fontSizes.display,
    fontWeight: '800',
    marginBottom: 8
  },
  intro: {
    color: colors.mutedText,
    fontSize: fontSizes.caption,
    lineHeight: 18
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
  fieldHeaderRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between'
  },
  fieldLabel: {
    color: colors.text,
    fontSize: fontSizes.label,
    fontWeight: '600'
  },
  counter: {
    color: colors.mutedText,
    fontSize: fontSizes.tiny
  },
  helperText: {
    color: colors.mutedText,
    fontSize: fontSizes.caption
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
  textArea: {
    minHeight: 132
  },
  divider: {
    backgroundColor: colors.border,
    height: 1,
    marginVertical: 14
  },
  errorText: {
    color: '#b3261e',
    fontSize: fontSizes.caption,
    fontWeight: '600'
  },
  error: {
    color: '#b3261e',
    fontSize: fontSizes.caption,
    fontWeight: '600',
    lineHeight: 18,
    marginTop: 16
  },
  submitButton: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 12,
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'center',
    marginTop: 20,
    minHeight: 50
  },
  submitButtonDisabled: {
    opacity: 0.5
  },
  submitButtonText: {
    color: colors.text,
    fontSize: fontSizes.bodyLarge,
    fontWeight: '800'
  },
  secondaryButton: {
    alignItems: 'center',
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: 1,
    justifyContent: 'center',
    marginTop: 12,
    minHeight: 50
  },
  secondaryButtonText: {
    color: colors.text,
    fontSize: fontSizes.bodyLarge,
    fontWeight: '700'
  },
  sentMark: {
    alignItems: 'center',
    alignSelf: 'center',
    backgroundColor: '#e3f8fa',
    borderRadius: 32,
    height: 64,
    justifyContent: 'center',
    width: 64
  },
  sentCheck: {
    color: '#006c4f',
    fontSize: fontSizes.display,
    fontWeight: '800'
  },
  sentTitle: {
    color: '#006c4f',
    fontSize: fontSizes.heading,
    fontWeight: '800',
    marginTop: 14,
    textAlign: 'center'
  },
  sentBody: {
    color: colors.mutedText,
    fontSize: fontSizes.caption,
    lineHeight: 18,
    marginTop: 8,
    textAlign: 'center'
  }
});
