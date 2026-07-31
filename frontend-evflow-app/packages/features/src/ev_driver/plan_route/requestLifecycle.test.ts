import { describe, expect, it } from 'vitest';
import { LatestRequestGate } from './requestLifecycle';

describe('latest request lifecycle', () => {
  it('aborts a stale request and prevents its response from being applied', () => {
    const gate = new LatestRequestGate();
    const first = gate.begin();
    const second = gate.begin();
    expect(first.signal.aborted).toBe(true);
    expect(gate.isCurrent(first.sequence)).toBe(false);
    expect(gate.isCurrent(second.sequence)).toBe(true);
  });
  it('cancels the active request when search closes', () => {
    const gate = new LatestRequestGate();
    const request = gate.begin(); gate.cancel();
    expect(request.signal.aborted).toBe(true);
    expect(gate.isCurrent(request.sequence)).toBe(false);
  });
});
