import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const directory = dirname(fileURLToPath(import.meta.url));
const heatmap = readFileSync(resolve(directory, '../DemandHeatmapScreen.tsx'), 'utf8');
const screen = readFileSync(resolve(directory, 'SavedSitesScreen.tsx'), 'utf8');
const detail = readFileSync(resolve(directory, '../site-feasibility/useSiteFeasibilityDetail.ts'), 'utf8');

describe('Saved Sites lifecycle', () => {
  it('loads bookmark status from the selected real site, independent of Epic 5 tabs', () => {
    const request = detail.indexOf('fetchPlannerSavedSiteStatus(siteId)');
    const effectStart = detail.lastIndexOf('useEffect(() => {', request);
    const effectEnd = detail.indexOf('}, [isMock, siteId]);', request);
    const effect = detail.slice(effectStart, effectEnd);
    expect(request).toBeGreaterThan(effectStart);
    expect(effectEnd).toBeGreaterThan(request);
    expect(effect).not.toContain('activeTab');
    expect(effect).toContain('isMock');
  });

  it('optimistically toggles and rolls back feasibility bookmarks', () => {
    expect(detail).toContain('setIsSaved(next);');
    expect(detail).toContain('setIsSaved(previous);');
    expect(detail).toContain('next ? savePlannerSite(siteId) : deletePlannerSavedSite(siteId)');
    expect(heatmap).toContain('onToggleSaved={detail.isMock ? undefined : detail.toggleSaved}');
  });

  it('shows loading, empty, error, list, and optimistic restore behavior', () => {
    expect(screen).toContain('Loading saved sites...');
    expect(screen).toContain('No saved sites yet.');
    expect(screen).toContain('Retry');
    expect(screen).toContain('current.filter((item) => item.cell_id !== site.cell_id)');
    expect(screen).toContain('restored.splice(Math.max(0, removedIndex), 0, site)');
    expect(screen).toContain("navigate('/business-dashboard/demand-heatmap')");
    expect(screen).toContain('<SiteFeasibilitySheet');
    expect(screen).toContain('setSelectedSite(site)');
  });

  it('opens as a full-height drawer and exposes saved-site pins when collapsed', () => {
    expect(screen).toContain('const [expanded, setExpanded] = useState(true)');
    expect(screen).toContain('height: sheetHeight');
    expect(screen).toContain('Collapse Saved Sites');
    expect(screen).toContain('plannerMarkers(savedSitesOnlyLayers');
    expect(screen).toContain('polygonLayers={[]}');
    expect(screen).toContain('onMarkerPress={onMarkerPress}');
    expect(screen).toContain('getSavedSitesMapView(items)');
  });

  it('uses the Heatmap detail zoom and drawer-aware centering for a selected site', () => {
    expect(screen).toContain('getDrawerAwareMapCenter(selectedSite, siteDetailZoom');
    expect(screen).toContain('const siteDetailZoom = 15');
    expect(screen).toContain('selectedMarkerId={selectedSite?.cell_id ?? null}');
  });
});
