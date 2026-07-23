import { describe, it, expect } from 'vitest';

import {
  REQUIRED_KWH_MIN,
  REQUIRED_KWH_MAX,
  isValidEmail,
  validatePassword,
  validateRequiredKWh,
  validateWalletBalance,
  formatCurrencyIDR,
  formatChargingDuration,
  getEstimatedChargingMinutes,
  formatTransactionDate
} from './validation';

describe('isValidEmail', () => {
  it('accepts a well-formed address (with surrounding whitespace trimmed)', () => {
    expect(isValidEmail('user@example.com')).toBe(true);
    expect(isValidEmail('  driver.name@sub.example.co  ')).toBe(true);
  });

  it('rejects when there is no "@" or the local part is empty', () => {
    expect(isValidEmail('noatsign.com')).toBe(false); // at === -1
    expect(isValidEmail('@example.com')).toBe(false); // at === 0
  });

  it('rejects when there is more than one "@"', () => {
    expect(isValidEmail('a@b@example.com')).toBe(false);
  });

  it('rejects whitespace inside the local part or domain', () => {
    expect(isValidEmail('bad local@example.com')).toBe(false);
    expect(isValidEmail('user@exa mple.com')).toBe(false);
  });

  it('rejects when the domain has no valid dot placement', () => {
    expect(isValidEmail('user@localhost')).toBe(false); // no dot
    expect(isValidEmail('user@.com')).toBe(false); // dot is first char
    expect(isValidEmail('user@example.')).toBe(false); // dot is last char
  });
});

describe('validatePassword', () => {
  it('requires a value', () => {
    expect(validatePassword('')).toBe('Password is required.');
  });

  it('enforces a minimum length', () => {
    expect(validatePassword('short')).toBe('Password must be at least 8 characters.');
  });

  it('returns null for an acceptable password', () => {
    expect(validatePassword('longenough')).toBeNull();
  });
});

describe('validateRequiredKWh', () => {
  it('rejects an empty string or non-finite input', () => {
    const message = `Enter a number from ${REQUIRED_KWH_MIN} to ${REQUIRED_KWH_MAX} kWh.`;
    expect(validateRequiredKWh('')).toBe(message);
    expect(validateRequiredKWh('   ')).toBe(message);
    expect(validateRequiredKWh('abc')).toBe(message);
    expect(validateRequiredKWh(Number.NaN)).toBe(message);
  });

  it('rejects values that are zero or negative', () => {
    expect(validateRequiredKWh(0)).toBe('Required energy must be greater than 0 kWh.');
    expect(validateRequiredKWh(-5)).toBe('Required energy must be greater than 0 kWh.');
  });

  it('rejects values below the minimum or above the maximum', () => {
    const rangeMessage = `Required energy must be between ${REQUIRED_KWH_MIN} and ${REQUIRED_KWH_MAX} kWh.`;
    expect(validateRequiredKWh(REQUIRED_KWH_MIN / 2)).toBe(rangeMessage);
    expect(validateRequiredKWh(REQUIRED_KWH_MAX + 1)).toBe(rangeMessage);
  });

  it('accepts an in-range numeric string or number', () => {
    expect(validateRequiredKWh('25')).toBeNull();
    expect(validateRequiredKWh(25)).toBeNull();
  });
});

describe('validateWalletBalance', () => {
  it('reports an unavailable balance when null or non-finite', () => {
    expect(validateWalletBalance(null, 100)).toBe('Wallet balance is unavailable. Please try again.');
    expect(validateWalletBalance(Number.POSITIVE_INFINITY, 100)).toBe(
      'Wallet balance is unavailable. Please try again.'
    );
  });

  it('reports insufficient funds when the amount due exceeds the balance', () => {
    expect(validateWalletBalance(50, 100)).toBe('Insufficient wallet balance. Please top up before paying.');
  });

  it('returns null when the balance covers the amount due', () => {
    expect(validateWalletBalance(100, 100)).toBeNull();
    expect(validateWalletBalance(150, 100)).toBeNull();
  });
});

describe('formatCurrencyIDR', () => {
  it('formats absolute amounts with the Rp prefix and id-ID grouping', () => {
    expect(formatCurrencyIDR(0)).toBe('Rp 0');
    expect(formatCurrencyIDR(-2500)).toBe(formatCurrencyIDR(2500));
    expect(formatCurrencyIDR(1000000)).toContain('Rp');
  });
});

describe('formatChargingDuration', () => {
  it('returns null for invalid or out-of-range durations', () => {
    expect(formatChargingDuration(null)).toBeNull();
    expect(formatChargingDuration(Number.NaN)).toBeNull();
    expect(formatChargingDuration(0)).toBeNull();
    expect(formatChargingDuration(24 * 60 + 1)).toBeNull();
  });

  it('formats durations under an hour in minutes', () => {
    expect(formatChargingDuration(45)).toBe('45 min');
  });

  it('formats durations of an hour or more, with and without trailing minutes', () => {
    expect(formatChargingDuration(90)).toBe('1 hr 30 min');
    expect(formatChargingDuration(120)).toBe('2 hr');
  });
});

describe('getEstimatedChargingMinutes', () => {
  it('returns null for invalid required kWh or charger power', () => {
    expect(getEstimatedChargingMinutes(Number.NaN, 50)).toBeNull();
    expect(getEstimatedChargingMinutes(0, 50)).toBeNull();
    expect(getEstimatedChargingMinutes(10, null)).toBeNull();
    expect(getEstimatedChargingMinutes(10, undefined)).toBeNull();
    expect(getEstimatedChargingMinutes(10, Number.POSITIVE_INFINITY)).toBeNull();
    expect(getEstimatedChargingMinutes(10, 0)).toBeNull();
  });

  it('computes minutes from required energy and charger power', () => {
    expect(getEstimatedChargingMinutes(50, 50)).toBe(60);
    expect(getEstimatedChargingMinutes(25, 50)).toBe(30);
  });
});

describe('formatTransactionDate', () => {
  it('formats an ISO date in the Asia/Jakarta timezone', () => {
    const formatted = formatTransactionDate('2024-01-15T00:00:00.000Z');
    expect(typeof formatted).toBe('string');
    expect(formatted.length).toBeGreaterThan(0);
  });

  it('honours caller-provided formatting options', () => {
    const formatted = formatTransactionDate('2024-01-15T12:00:00.000Z', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
    expect(formatted).toContain('2024');
  });
});
