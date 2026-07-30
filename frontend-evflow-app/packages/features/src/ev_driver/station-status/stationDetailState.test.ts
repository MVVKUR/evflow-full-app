import { describe, expect, it } from 'vitest';
import { availableStationStatusFixture } from './mockStationStatus';
import { getDrawerAwareMapCenter, getDrawerModeAfterClosingStationDetail, isCurrentStationStatusRequest, loadValidStationStatus, shouldRenderSearchBar } from './stationDetailState';
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

  it('centers a selected marker in the visible map above the drawer', () => {
    const station = { latitude: -6.2, longitude: 106.8 };
    const collapsedCenter = getDrawerAwareMapCenter(station, 15, 204);
    const expandedCenter = getDrawerAwareMapCenter(station, 15, 640);
    expect(collapsedCenter.longitude).toBe(station.longitude);
    expect(collapsedCenter.latitude).toBeLessThan(station.latitude);
    expect(expandedCenter.latitude).toBeLessThan(collapsedCenter.latitude);
  });
});
