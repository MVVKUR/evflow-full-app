import { describe, expect, it } from 'vitest';
import { aggregateConnectorStatuses, resolveConnectorEstimate } from './aggregateConnectorStatuses';
import type { ConnectorOperationalStatus, LiveConnectorStatus } from './types';

function connector(id: string, status: ConnectorOperationalStatus, wait: number | null = null): LiveConnectorStatus {
  return {
    connectorId: id,
    connectorType: 'CCS2',
    speedTier: 'ultra_fast',
    powerKw: 180,
    status,
    estimatedWaitMinutes: wait,
    estimatedAvailableAt: null
  };
}

describe('aggregateConnectorStatuses', () => {
  it('reports all connectors available', () => {
    const result = aggregateConnectorStatuses([connector('1', 'available'), connector('2', 'available')]);
    expect(result).toMatchObject({ state: 'available', availableCount: 2, totalCount: 2 });
    expect(result.subtitle).toBe('2 of 2 connectors available right now');
  });

  it('reports partial availability and preserves mixed group counts', () => {
    const result = aggregateConnectorStatuses([
      connector('1', 'available'),
      connector('2', 'occupied', 8),
      connector('3', 'out_of_service')
    ]);
    expect(result.state).toBe('available');
    expect(result.groups[0]).toMatchObject({ availableCount: 1, occupiedCount: 1, outOfServiceCount: 1 });
  });

  it('reports all connectors occupied with wait times', () => {
    const result = aggregateConnectorStatuses([connector('1', 'occupied', 15), connector('2', 'occupied', 8)]);
    expect(result).toMatchObject({ state: 'occupied', occupiedCount: 2 });
    expect(result.earliestEstimate?.minutes).toBe(8);
    expect(result.subtitle).toBe('Est. ~8 mins left');
  });

  it('reports all connectors out of service', () => {
    const result = aggregateConnectorStatuses([connector('1', 'out_of_service'), connector('2', 'out_of_service')]);
    expect(result).toMatchObject({ state: 'out_of_service', outOfServiceCount: 2, title: 'Temporarily Unavailable' });
  });

  it('reports mixed occupied and out-of-service connectors as occupied', () => {
    const result = aggregateConnectorStatuses([connector('1', 'occupied', 12), connector('2', 'out_of_service')]);
    expect(result).toMatchObject({ state: 'occupied', occupiedCount: 1, outOfServiceCount: 1 });
  });

  it('reports unknown when no connector has a valid operational status', () => {
    const result = aggregateConnectorStatuses([connector('1', 'unknown'), connector('2', 'unknown')]);
    expect(result).toMatchObject({ state: 'unknown', title: 'Live Status Unavailable' });
  });

  it('selects the earliest estimate and prefers wait minutes over a timestamp', () => {
    const absolute = { ...connector('2', 'occupied'), estimatedAvailableAt: '2026-07-28T10:30:00.000Z' };
    const result = aggregateConnectorStatuses(
      [connector('1', 'occupied', 9), absolute],
      new Date('2026-07-28T10:00:00.000Z')
    );
    expect(result.earliestEstimate?.minutes).toBe(9);
    expect(resolveConnectorEstimate(
      { estimatedWaitMinutes: 7, estimatedAvailableAt: '2026-07-28T10:01:00.000Z' },
      new Date('2026-07-28T10:00:00.000Z')
    )).toEqual({ availableAt: null, minutes: 7 });
  });

  it('never returns a negative absolute countdown', () => {
    expect(resolveConnectorEstimate(
      { estimatedWaitMinutes: null, estimatedAvailableAt: '2026-07-28T09:00:00.000Z' },
      new Date('2026-07-28T10:00:00.000Z')
    )?.minutes).toBe(0);
  });
});
