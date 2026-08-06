import { describe, it, expect } from 'vitest';

import { describeSupportFailure, describeSupportSuccess, formatWait } from './supportMessages';

describe('describeSupportFailure', () => {
  it('tells the driver to check their connection when the request never reached the API', () => {
    expect(describeSupportFailure('network')).toContain('internet connection');
  });

  it('tells the driver to use another channel when support email is not configured', () => {
    const copy = describeSupportFailure('email_disabled');
    expect(copy).toContain('not set up right now');
    expect(copy).toContain('another channel');
  });

  it('tells the driver to wait when rate limited, with no hint when the API sent none', () => {
    expect(describeSupportFailure('rate_limited')).toBe(
      'Too many messages sent. Please wait a moment before sending another one.'
    );
  });

  it('includes the Retry-After hint when the API sent one', () => {
    expect(describeSupportFailure('rate_limited', 45)).toContain('45 seconds');
    expect(describeSupportFailure('rate_limited', 120)).toContain('2 minutes');
  });

  it('tells the driver to log in again when the session is rejected', () => {
    expect(describeSupportFailure('unauthorized')).toContain('Log in again');
  });

  it('asks the driver to shorten the message when the API rejected the payload', () => {
    expect(describeSupportFailure('invalid')).toContain('Shorten it');
  });

  it('falls back to a retry-later message for server failures', () => {
    expect(describeSupportFailure('server')).toContain('try again in a few minutes');
  });

  it('gives every failure kind its own distinct copy', () => {
    const kinds = ['network', 'email_disabled', 'rate_limited', 'unauthorized', 'invalid', 'server'] as const;
    const copies = kinds.map((kind) => describeSupportFailure(kind));
    expect(new Set(copies).size).toBe(kinds.length);
  });
});

describe('formatWait', () => {
  it('falls back to a vague wait for non-positive or non-finite input', () => {
    expect(formatWait(0)).toBe('a moment');
    expect(formatWait(-5)).toBe('a moment');
    expect(formatWait(Number.NaN)).toBe('a moment');
  });

  it('formats sub-minute waits in seconds, singular and plural', () => {
    expect(formatWait(1)).toBe('1 second');
    expect(formatWait(59)).toBe('59 seconds');
  });

  it('rounds partial seconds up so the hint is never too short', () => {
    expect(formatWait(1.2)).toBe('2 seconds');
  });

  it('formats waits of a minute or more in minutes, rounding up', () => {
    expect(formatWait(60)).toBe('1 minute');
    expect(formatWait(61)).toBe('2 minutes');
    expect(formatWait(300)).toBe('5 minutes');
  });
});

describe('describeSupportSuccess', () => {
  it('names the address support will answer', () => {
    expect(describeSupportSuccess('driver@example.com')).toContain('driver@example.com');
  });

  it('warns that a ticket with no reply address cannot be answered', () => {
    const copy = describeSupportSuccess(null);
    expect(copy).toContain('Message sent');
    expect(copy).toContain('cannot write back');
  });
});
