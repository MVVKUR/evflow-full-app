import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const screenSource = readFileSync(resolve(currentDirectory, '../DemandHeatmapScreen.tsx'), 'utf8');
const financialTabSource = readFileSync(resolve(currentDirectory, 'FinancialProjectionsTab.tsx'), 'utf8');

describe('Site Feasibility ROI lifecycle contract', () => {
  it('attaches ROI loading to the selected-site lifecycle rather than tab state', () => {
    const request = screenSource.indexOf('getSiteFinancialProjection(selectedSiteId)');
    const effectStart = screenSource.lastIndexOf('useEffect(() => {', request);
    const effectEnd = screenSource.indexOf('}, [financialRequestKey]);', request);
    const effect = screenSource.slice(effectStart, effectEnd + '}, [financialRequestKey]);'.length);

    expect(request).toBeGreaterThan(effectStart);
    expect(effectEnd).toBeGreaterThan(request);
    expect(effect).toContain('isMockOptimalSiteId(selectedSiteId)');
    expect(effect).toContain('getSiteFinancialProjection(selectedSiteId)');
    expect(effect).not.toContain('siteTab');
    expect(effect).not.toContain('siteData');
  });

  it('renders the metric grid directly after Projection Summary with no disclaimer', () => {
    expect(financialTabSource).toMatch(/PROJECTION SUMMARY<\/Text>\s*<View style=\{styles\.grid\}>/);
    expect(financialTabSource).not.toContain('styles.disclosure');
    expect(financialTabSource).not.toContain('compactProjectionBasis');
    expect(financialTabSource).not.toContain('Projection based on planner-provided');
  });
});
