import { describe, expect, it } from 'vitest';
import { connectorStatusPalette } from './connectorStatusPalette';

/** Relative luminance per WCAG 2.1, from a #rrggbb string. */
function luminance(hex: string): number {
  const channel = (i: number) => {
    const v = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
}

function contrast(fg: string, bg: string): number {
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

describe('connectorStatusPalette (AC 3.1.2)', () => {
  it('assigns the colours the AC names', () => {
    // Green available, red occupied, grey out of service. The regression this
    // guards: red used to mark out-of-service while occupied was amber.
    expect(connectorStatusPalette.free.text).toBe('#0B7A41');
    expect(connectorStatusPalette.inUse.text).toBe('#C62828');
    expect(connectorStatusPalette.outOfService.text).toBe('#55656A');
  });

  it('keeps every label readable on its own fill', () => {
    // "high-contrast color coding" in the AC. 4.5:1 is the WCAG AA floor for
    // text this size.
    for (const tone of ['free', 'inUse', 'outOfService'] as const) {
      const { text, background } = connectorStatusPalette[tone];
      expect(contrast(text, background), tone).toBeGreaterThanOrEqual(4.5);
    }
    expect(contrast(connectorStatusPalette.unknown.text, '#FFFFFF')).toBeGreaterThanOrEqual(3);
  });

  it('keeps the three named statuses distinguishable from each other', () => {
    const { free, inUse, outOfService } = connectorStatusPalette;
    expect(new Set([free.text, inUse.text, outOfService.text]).size).toBe(3);
  });

  it('never lets "unknown" pass for a confirmed fault', () => {
    // Same grey family, but no fill: an unreadable status must not look like
    // a plug we know is broken.
    expect(connectorStatusPalette.unknown.text).not.toBe(connectorStatusPalette.outOfService.text);
    expect(connectorStatusPalette.unknown.background).toBe('transparent');
  });
});
