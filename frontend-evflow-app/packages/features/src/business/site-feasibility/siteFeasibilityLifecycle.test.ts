import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const detailSource = readFileSync(resolve(currentDirectory, 'useSiteFeasibilityDetail.ts'), 'utf8');
const financialTabSource = readFileSync(resolve(currentDirectory, 'FinancialProjectionsTab.tsx'), 'utf8');

describe('Site Feasibility ROI lifecycle contract', () => {
  it('attaches ROI loading to the selected-site lifecycle rather than tab state', () => {
    const request = detailSource.indexOf('getSiteFinancialProjection(siteId)');
    const effectStart = detailSource.lastIndexOf('useEffect(() => {', request);
    const effectEnd = detailSource.indexOf('}, [financialRetry, isMock, siteId]);', request);
    const effect = detailSource.slice(effectStart, effectEnd);

    expect(request).toBeGreaterThan(effectStart);
    expect(effectEnd).toBeGreaterThan(request);
    expect(effect).toContain('isMock');
    expect(effect).toContain('getSiteFinancialProjection(siteId)');
    expect(effect).not.toContain('activeTab');
  });

  it('renders the metric grid directly after Projection Summary with no disclaimer', () => {
    expect(financialTabSource).toMatch(/PROJECTION SUMMARY<\/Text>\s*<View style=\{styles\.grid\}>/);
    expect(financialTabSource).not.toContain('styles.disclosure');
    expect(financialTabSource).not.toContain('compactProjectionBasis');
    expect(financialTabSource).not.toContain('Projection based on planner-provided');
  });
});
