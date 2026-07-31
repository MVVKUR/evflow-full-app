import { describe, expect, it } from 'vitest';
import { availableStationStatusFixture } from './mockStationStatus';
import { getDrawerAwareMapCenter, getDrawerModeAfterClosingStationDetail, getFreshCachedStationStatus, invalidateCachedStationStatus, isCurrentStationStatusRequest, loadValidStationStatus, shouldRenderSearchBar, stationStatusCacheTtlMs, type CachedStationStatus } from './stationDetailState';
import type { StationStatusLoader } from './types';

describe('station detail state', () => {
  it('hides the search bar during detail mode', () => {
    expect(shouldRenderSearchBar('detail')).toBe(false);
  });

  it('restores the search bar after closing detail', () => {
    const restoredMode = getDrawerModeAfterClosingStationDetail();
    expect(restoredMode).toBe('results');
    expect(shouldRenderSearchBar(restoredMode)).toBe(true);
  });

  it('allows a loader error to be retried successfully', async () => {
    let attempt = 0;
    const loader: StationStatusLoader = async (stationId) => {
      attempt += 1;
      if (attempt === 1) throw new Error('status offline');
      return { ...availableStationStatusFixture, stationId };
    };
    await expect(loadValidStationStatus(loader, 'station-a')).rejects.toThrow('status offline');
    await expect(loadValidStationStatus(loader, 'station-a')).resolves.toMatchObject({ stationId: 'station-a' });
    expect(attempt).toBe(2);
  });

  it('ignores a stale loader response after the selected station changes', () => {
    expect(isCurrentStationStatusRequest({ requestId: 1, stationId: 'station-a' }, 2, 'station-b')).toBe(false);
    expect(isCurrentStationStatusRequest({ requestId: 2, stationId: 'station-b' }, 2, 'station-b')).toBe(true);
  });

  it('uses cached live status only within the TTL', () => {
    const fetchedAt = 1_000;
    const cache = new Map<string, CachedStationStatus>([
      ['station-a', { data: { ...availableStationStatusFixture, stationId: 'station-a' }, fetchedAt }]
    ]);

    expect(getFreshCachedStationStatus(cache, 'station-a', fetchedAt + stationStatusCacheTtlMs - 1))
      .toMatchObject({ stationId: 'station-a' });
    expect(getFreshCachedStationStatus(cache, 'station-a', fetchedAt + stationStatusCacheTtlMs)).toBeNull();
  });

  it('invalidates the selected station cache for retry', () => {
    const cache = new Map<string, CachedStationStatus>([
      ['station-a', { data: { ...availableStationStatusFixture, stationId: 'station-a' }, fetchedAt: 1_000 }],
      ['station-b', { data: { ...availableStationStatusFixture, stationId: 'station-b' }, fetchedAt: 1_000 }]
    ]);

    invalidateCachedStationStatus(cache, 'station-a');
    expect(cache.has('station-a')).toBe(false);
    expect(cache.has('station-b')).toBe(true);
  });

  it('centers a selected marker in the visible map above the drawer', () => {
    const station = { latitude: -6.2, longitude: 106.8 };
    const collapsedCenter = getDrawerAwareMapCenter(station, 15, 204);
    const expandedCenter = getDrawerAwareMapCenter(station, 15, 640);
    expect(collapsedCenter.longitude).toBe(station.longitude);
    expect(collapsedCenter.latitude).toBeLessThan(station.latitude);
    expect(expandedCenter.latitude).toBeLessThan(collapsedCenter.latitude);
  });
});
