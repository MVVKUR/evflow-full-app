/**
 * AC 3.1.2: connector status must be distinguishable by high-contrast colour
 * AND by a text label. Green for Available, Red for Occupied, Grey for Out of
 * Service.
 *
 * Occupied is red because the AC says so. It is worth recording that this is
 * not the obvious choice: a plug in use is healthy and frees itself in
 * minutes, while a broken one does not, and amber used to carry that
 * difference. With both drawn from the red/grey pair, the TEXT label is what
 * separates "wait here" from "do not bother", which is why no status is ever
 * rendered as colour alone.
 *
 * `unknown` is deliberately NOT the same grey as out-of-service: "the plug is
 * broken" and "we could not read this plug" are different facts, and an
 * unreadable status must never look like a confirmed fault. It drops the
 * tinted fill entirely so the two never read as one state.
 */
export type ConnectorStatusTone = 'free' | 'inUse' | 'outOfService' | 'unknown';

export type StatusPalette = {
  /** Pill fill. Transparent for `unknown`, which makes no claim. */
  background: string;
  /** Label and figure colour. */
  text: string;
};

export const connectorStatusPalette: Record<ConnectorStatusTone, StatusPalette> = {
  free: { background: '#EAF8F0', text: '#0B7A41' },
  inUse: { background: '#FBEAEA', text: '#C62828' },
  outOfService: { background: '#EDF0F1', text: '#55656A' },
  unknown: { background: 'transparent', text: '#8A979B' }
};
