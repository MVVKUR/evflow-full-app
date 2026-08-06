// Type-only import, so this module stays free of react-native at runtime and
// its vitest suite needs no stubs. See supportValidation.ts for the same note.
import type { SupportFailureKind } from '../../../shared/src/support/api';

export const SUPPORT_INVALID_FORM_MESSAGE = 'Please fix the highlighted fields before sending.';

// The API does not fall back to the account email: a ticket with no reply-to
// reaches support as "Reply-to: not supplied" and cannot be answered. Promising
// a reply anyway would be the one thing the driver cannot check for themselves.
export function describeSupportSuccess(replyTo: string | null): string {
  return replyTo
    ? `Message sent. The EV-FLOW support team will reply to ${replyTo}.`
    : 'Message sent. You did not leave a reply address, so support can read your message but cannot write back.';
}

// Every branch is deliberately distinct: the driver's next action differs per
// failure. Retrying a 503 is pointless, retrying a 429 works after a wait, and
// a network failure is fixable on the device.
export function describeSupportFailure(
  kind: SupportFailureKind,
  retryAfterSeconds: number | null = null
): string {
  switch (kind) {
    case 'network':
      return 'We could not reach EV-FLOW. Check your internet connection and try again.';

    case 'email_disabled':
      return 'Support email is not set up right now, so this message cannot be delivered. Please reach the EV-FLOW team through another channel and try again later.';

    case 'rate_limited':
      return retryAfterSeconds === null
        ? 'Too many messages sent. Please wait a moment before sending another one.'
        : `Too many messages sent. Please wait about ${formatWait(retryAfterSeconds)} before sending another one.`;

    case 'unauthorized':
      return 'Your session has expired. Log in again, then resend your message.';

    case 'blocked':
      return 'This app build cannot reach support from here. Open EV-FLOW from its official address and try again.';

    case 'invalid':
      return 'Your message was rejected. Shorten it, check the reply email, and try again.';

    default:
      return 'Support could not accept your message right now. Please try again in a few minutes.';
  }
}

export function formatWait(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return 'a moment';
  }

  const wholeSeconds = Math.ceil(seconds);

  if (wholeSeconds < 60) {
    return `${wholeSeconds} second${wholeSeconds === 1 ? '' : 's'}`;
  }

  const minutes = Math.ceil(wholeSeconds / 60);
  return `${minutes} minute${minutes === 1 ? '' : 's'}`;
}
