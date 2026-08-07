import { describe, expect, it } from 'vitest';
import { buildNavigationMarkers } from './navigationMarkers';

const destination = { latitude: -6.1922, longitude: 106.7994 };

function station(id: string, name: string | null = 'SPKLU Test') {
  return { station: { id, name, latitude: -6.25, longitude: 106.72 } };
}

function plan(over: Record<string, unknown> = {}) {
  return { recommended_stop: null, user_requested_stop: null, ...over } as never;
}

describe('buildNavigationMarkers', () => {
  it('always draws the destination', () => {
    const m = buildNavigationMarkers(plan(), destination, 'Slipi');
    expect(m).toHaveLength(1);
    expect(m[0]).toMatchObject({ id: 'destination', label: 'Slipi', type: 'destination' });
  });

  // The regression this file exists for: navigating a route planned around an
  // SPKLU used to show no pin for it at all.
  it('draws the recommended charging stop alongside the destination', () => {
    const m = buildNavigationMarkers(plan({ recommended_stop: station('pln_spklu-70') }), destination, 'Slipi');
    expect(m).toHaveLength(2);
    expect(m[1]).toMatchObject({ id: 'pln_spklu-70', type: 'charging_stop', label: 'SPKLU Test' });
  });

  it('prefers a stop the driver forced over the recommended one', () => {
    const m = buildNavigationMarkers(
      plan({ recommended_stop: station('recommended'), user_requested_stop: station('chosen') }),
      destination, 'Slipi'
    );
    expect(m.map((x) => x.id)).toEqual(['destination', 'chosen']);
  });

  it('falls back to a readable label when the station has no name', () => {
    const m = buildNavigationMarkers(plan({ recommended_stop: station('x', null) }), destination, 'Slipi');
    expect(m[1].label).toBe('Charging stop');
  });
});
