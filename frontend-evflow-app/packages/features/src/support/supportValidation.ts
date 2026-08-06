// Deep relative imports instead of the "@evflow/shared" barrel: this module is
// covered by a node-environment vitest suite, and the barrel pulls in
// api/baseUrl -> react-native, which the suite would then have to stub. Both
// targets here are dependency-free modules. `SupportTicketRequest` is a
// type-only import, so it is erased and never loads its module at runtime.
import { isValidEmail } from '../../../shared/src/validation';
import type { SupportTicketRequest } from '../../../shared/src/support/api';

// Mirrors api/models.py SupportTicketRequest exactly. Diverging would either
// reject something the API accepts or let through a request the API answers 422
// to, and the 422 body is the one thing this screen must never show.
export const SUPPORT_SUBJECT_MIN_LENGTH = 3;
export const SUPPORT_SUBJECT_MAX_LENGTH = 200;
export const SUPPORT_MESSAGE_MIN_LENGTH = 10;
export const SUPPORT_MESSAGE_MAX_LENGTH = 5000;
export const SUPPORT_EMAIL_MAX_LENGTH = 254;

export type SupportFormValues = {
  subject: string;
  message: string;
  replyToEmail: string;
};

export type SupportFormErrors = {
  subject: string | null;
  message: string | null;
  replyToEmail: string | null;
};

export const EMPTY_SUPPORT_FORM: SupportFormValues = {
  subject: '',
  message: '',
  replyToEmail: ''
};

export function validateSupportSubject(value: string): string | null {
  const trimmed = value.trim();

  if (!trimmed) {
    return 'Subject is required.';
  }

  if (trimmed.length < SUPPORT_SUBJECT_MIN_LENGTH) {
    return `Subject must be at least ${SUPPORT_SUBJECT_MIN_LENGTH} characters.`;
  }

  if (trimmed.length > SUPPORT_SUBJECT_MAX_LENGTH) {
    return `Subject must be ${SUPPORT_SUBJECT_MAX_LENGTH} characters or fewer.`;
  }

  // The API writes the subject into a MIME header and rejects line breaks as an
  // injection attempt. Catching it here keeps a pasted multi-line subject from
  // coming back as an opaque 422.
  if (containsLineBreak(trimmed)) {
    return 'Subject must be a single line.';
  }

  return null;
}

export function validateSupportMessage(value: string): string | null {
  const trimmed = value.trim();

  if (!trimmed) {
    return 'Message is required.';
  }

  if (trimmed.length < SUPPORT_MESSAGE_MIN_LENGTH) {
    return `Message must be at least ${SUPPORT_MESSAGE_MIN_LENGTH} characters.`;
  }

  if (trimmed.length > SUPPORT_MESSAGE_MAX_LENGTH) {
    return `Message must be ${SUPPORT_MESSAGE_MAX_LENGTH} characters or fewer.`;
  }

  return null;
}

export function validateSupportReplyEmail(value: string): string | null {
  const trimmed = value.trim();

  // Optional field: a blank value lets the backend reply to the account email.
  if (!trimmed) {
    return null;
  }

  if (trimmed.length > SUPPORT_EMAIL_MAX_LENGTH) {
    return `Email must be ${SUPPORT_EMAIL_MAX_LENGTH} characters or fewer.`;
  }

  // isValidEmail rejects any whitespace, so CR/LF header injection is covered.
  if (!isValidEmail(trimmed)) {
    return 'Enter a valid email address.';
  }

  return null;
}

function containsLineBreak(value: string): boolean {
  return value.includes('\r') || value.includes('\n');
}

export function validateSupportForm(values: SupportFormValues): SupportFormErrors {
  return {
    subject: validateSupportSubject(values.subject),
    message: validateSupportMessage(values.message),
    replyToEmail: validateSupportReplyEmail(values.replyToEmail)
  };
}

export function hasSupportFormErrors(errors: SupportFormErrors): boolean {
  return errors.subject !== null || errors.message !== null || errors.replyToEmail !== null;
}

export function isSupportFormSubmittable(values: SupportFormValues): boolean {
  return !hasSupportFormErrors(validateSupportForm(values));
}

export function buildSupportTicketRequest(values: SupportFormValues): SupportTicketRequest {
  const replyToEmail = values.replyToEmail.trim();

  return {
    subject: values.subject.trim(),
    message: values.message.trim(),
    // Trimmed but not lower-cased: this becomes a Reply-To header, and the local
    // part of an address is case-sensitive. null rather than "" so the API sees
    // the field as absent.
    reply_to: replyToEmail || null
  };
}

export function remainingCharacters(value: string, maxLength: number): number {
  return maxLength - value.trim().length;
}
