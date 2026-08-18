import { describe, expect, it } from 'vitest';
import { defaultPlannerLayers, generateMockOptimalSites, jakartaViewport, prioritySemanticCategory, viabilityTier } from './demandHeatmap';

describe('Demand Heatmap planning state', () => {
  it('enables recommendations and demand analysis by default, with supplementary layers off', () => {
    expect(defaultPlannerLayers).toEqual({
      optimalSites: true,
      demandHeatmap: true,
      existingSpklus: false,
      commercialPois: false,
      populationDensity: false,
      landUse: false
    });
  });

  it('maps viability score tiers according to the planning thresholds', () => {
    expect(viabilityTier(94)).toBe(1);
    expect(viabilityTier(85)).toBe(1);
    expect(viabilityTier(84)).toBe(2);
    expect(viabilityTier(70)).toBe(2);
    expect(viabilityTier(69)).toBeNull();
  });

  it('uses readable semantic priority categories', () => {
    expect(prioritySemanticCategory('high')).toBe('High Priority');
    expect(prioritySemanticCategory('moderate')).toBe('Moderate Priority');
    expect(prioritySemanticCategory('low')).toBe('Low Priority');
  });

  it('generates deterministic recommendations inside the supplied viewport', () => {
    const sites = generateMockOptimalSites(jakartaViewport);
    expect(sites.map((site) => site.score)).toEqual([94, 88, 82, 76, 72]);
    expect(sites.every((site) => site.latitude >= jakartaViewport.south && site.latitude <= jakartaViewport.north && site.longitude >= jakartaViewport.west && site.longitude <= jakartaViewport.east)).toBe(true);
  });
});
