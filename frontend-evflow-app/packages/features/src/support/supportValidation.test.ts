import { describe, it, expect } from 'vitest';

import {
  buildSupportTicketRequest,
  EMPTY_SUPPORT_FORM,
  hasSupportFormErrors,
  isSupportFormSubmittable,
  remainingCharacters,
  SUPPORT_EMAIL_MAX_LENGTH,
  SUPPORT_MESSAGE_MAX_LENGTH,
  SUPPORT_MESSAGE_MIN_LENGTH,
  SUPPORT_SUBJECT_MAX_LENGTH,
  SUPPORT_SUBJECT_MIN_LENGTH,
  validateSupportForm,
  validateSupportMessage,
  validateSupportReplyEmail,
  validateSupportSubject,
  type SupportFormValues
} from './supportValidation';

function form(overrides: Partial<SupportFormValues> = {}): SupportFormValues {
  return {
    subject: 'Charger stuck',
    message: 'The connector would not unlock after my session ended.',
    replyToEmail: '',
    ...overrides
  };
}

describe('validateSupportSubject', () => {
  it('requires a value, treating whitespace as empty', () => {
    expect(validateSupportSubject('')).toBe('Subject is required.');
    expect(validateSupportSubject('   ')).toBe('Subject is required.');
  });

  it('enforces the minimum length after trimming', () => {
    const message = `Subject must be at least ${SUPPORT_SUBJECT_MIN_LENGTH} characters.`;
    expect(validateSupportSubject('ab')).toBe(message);
    expect(validateSupportSubject('   ab   ')).toBe(message);
  });

  it('rejects a subject containing a line break, which the API treats as header injection', () => {
    expect(validateSupportSubject('Charger stuck\nBcc: someone@example.com')).toBe(
      'Subject must be a single line.'
    );
    expect(validateSupportSubject('Charger\rstuck')).toBe('Subject must be a single line.');
  });

  it('enforces the maximum length after trimming', () => {
    const tooLong = 'a'.repeat(SUPPORT_SUBJECT_MAX_LENGTH + 1);
    expect(validateSupportSubject(tooLong)).toBe(
      `Subject must be ${SUPPORT_SUBJECT_MAX_LENGTH} characters or fewer.`
    );
    expect(validateSupportSubject(`  ${'a'.repeat(SUPPORT_SUBJECT_MAX_LENGTH)}  `)).toBeNull();
  });

  it('accepts a subject at both boundaries', () => {
    expect(validateSupportSubject('a'.repeat(SUPPORT_SUBJECT_MIN_LENGTH))).toBeNull();
    expect(validateSupportSubject('a'.repeat(SUPPORT_SUBJECT_MAX_LENGTH))).toBeNull();
  });
});

describe('validateSupportMessage', () => {
  it('requires a value, treating whitespace as empty', () => {
    expect(validateSupportMessage('')).toBe('Message is required.');
    expect(validateSupportMessage('\n\t ')).toBe('Message is required.');
  });

  it('enforces the minimum length after trimming', () => {
    expect(validateSupportMessage('too short')).toBe(
      `Message must be at least ${SUPPORT_MESSAGE_MIN_LENGTH} characters.`
    );
  });

  it('enforces the maximum length after trimming', () => {
    expect(validateSupportMessage('a'.repeat(SUPPORT_MESSAGE_MAX_LENGTH + 1))).toBe(
      `Message must be ${SUPPORT_MESSAGE_MAX_LENGTH} characters or fewer.`
    );
  });

  it('accepts a message at both boundaries', () => {
    expect(validateSupportMessage('a'.repeat(SUPPORT_MESSAGE_MIN_LENGTH))).toBeNull();
    expect(validateSupportMessage('a'.repeat(SUPPORT_MESSAGE_MAX_LENGTH))).toBeNull();
  });
});

describe('validateSupportReplyEmail', () => {
  it('accepts a blank value because the field is optional', () => {
    expect(validateSupportReplyEmail('')).toBeNull();
    expect(validateSupportReplyEmail('   ')).toBeNull();
  });

  it('checks the format only once something is typed', () => {
    expect(validateSupportReplyEmail('not-an-email')).toBe('Enter a valid email address.');
    expect(validateSupportReplyEmail('driver@example')).toBe('Enter a valid email address.');
    expect(validateSupportReplyEmail('  driver@example.com  ')).toBeNull();
  });

  it('rejects an address longer than the maximum', () => {
    const longLocal = 'a'.repeat(SUPPORT_EMAIL_MAX_LENGTH);
    expect(validateSupportReplyEmail(`${longLocal}@example.com`)).toBe(
      `Email must be ${SUPPORT_EMAIL_MAX_LENGTH} characters or fewer.`
    );
  });
});

describe('validateSupportForm / hasSupportFormErrors', () => {
  it('reports no errors for a well-formed ticket without a reply email', () => {
    const errors = validateSupportForm(form());
    expect(errors).toEqual({ subject: null, message: null, replyToEmail: null });
    expect(hasSupportFormErrors(errors)).toBe(false);
    expect(isSupportFormSubmittable(form())).toBe(true);
  });

  it('reports every failing field at once', () => {
    const errors = validateSupportForm({ subject: '', message: '', replyToEmail: 'nope' });
    expect(errors.subject).toBe('Subject is required.');
    expect(errors.message).toBe('Message is required.');
    expect(errors.replyToEmail).toBe('Enter a valid email address.');
    expect(hasSupportFormErrors(errors)).toBe(true);
  });

  it('treats the empty form as not submittable', () => {
    expect(isSupportFormSubmittable(EMPTY_SUPPORT_FORM)).toBe(false);
  });

  it('blocks submission when only the optional email is malformed', () => {
    expect(isSupportFormSubmittable(form({ replyToEmail: 'bad@@example.com' }))).toBe(false);
  });
});

describe('buildSupportTicketRequest', () => {
  it('trims the subject and message', () => {
    const request = buildSupportTicketRequest(form({ subject: '  Charger stuck  ', message: '  Long enough message.  ' }));
    expect(request.subject).toBe('Charger stuck');
    expect(request.message).toBe('Long enough message.');
  });

  it('sends null rather than an empty string when no reply email was typed', () => {
    expect(buildSupportTicketRequest(form({ replyToEmail: '   ' })).reply_to).toBeNull();
  });

  it('trims a supplied reply email but preserves its case, since it becomes a Reply-To header', () => {
    expect(buildSupportTicketRequest(form({ replyToEmail: '  Driver@Example.COM ' })).reply_to).toBe(
      'Driver@Example.COM'
    );
  });

  it('names the payload fields the API expects', () => {
    expect(Object.keys(buildSupportTicketRequest(form())).sort()).toEqual([
      'message',
      'reply_to',
      'subject'
    ]);
  });
});

describe('remainingCharacters', () => {
  it('counts down from the maximum using the trimmed length', () => {
    expect(remainingCharacters('', SUPPORT_MESSAGE_MAX_LENGTH)).toBe(SUPPORT_MESSAGE_MAX_LENGTH);
    expect(remainingCharacters('  abc  ', 10)).toBe(7);
  });

  it('goes negative once the value is over the maximum', () => {
    expect(remainingCharacters('abcdef', 4)).toBe(-2);
  });
});
