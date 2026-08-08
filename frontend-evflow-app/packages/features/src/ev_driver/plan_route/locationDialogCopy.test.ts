import { describe, expect, it } from 'vitest';
import { getLocationDialogCopy } from './locationDialogCopy';

describe('getLocationDialogCopy', () => {
  it('invites on the first showing', () => {
    const copy = getLocationDialogCopy('undetermined', 0);
    expect(copy.primaryLabel).toBe('Allow location');
    expect(copy.body).toContain('route origin');
  });

  it('never repeats the same words after a failed attempt', () => {
    // The dead-button bug: pressing Allow re-rendered identical copy.
    const first = getLocationDialogCopy('undetermined', 0);
    const second = getLocationDialogCopy('undetermined', 1);
    expect(second.body).not.toBe(first.body);
    expect(second.primaryLabel).toBe('Try again');
  });

  it('names the real blocker so the driver knows where to fix it', () => {
    expect(getLocationDialogCopy('denied', 1).body).toMatch(/browser settings/i);
    expect(getLocationDialogCopy('unavailable', 1).body).toMatch(/system settings/i);
    expect(getLocationDialogCopy('gps_error', 1).title).toBe('Location unavailable');
  });

  it('always offers the manual way out', () => {
    for (const status of ['undetermined', 'denied', 'unavailable', 'gps_error'] as const) {
      expect(getLocationDialogCopy(status, 1).hint).toBeTruthy();
    }
  });
});
