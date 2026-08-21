import { describe, expect, it } from 'vitest';
import { businessPlannerTabs, getBusinessPlannerNavigationItems, getBusinessPlannerPath, getBusinessPlannerTab } from './businessPlannerNavigation';

describe('Business Planner navigation', () => {
  it('defines Heatmap, Saved Sites, and Profile in order', () => {
    expect(businessPlannerTabs).toEqual(['demand-heatmap', 'saved-sites', 'profile']);
    expect(getBusinessPlannerNavigationItems().map((item) => item.label)).toEqual([
      'Heatmap',
      'Saved Sites',
      'Profile'
    ]);
  });

  it('provides a route for every tab and defaults unknown paths to Demand Heatmap', () => {
    const items = getBusinessPlannerNavigationItems();

    expect(items.every((item) => !item.disabled)).toBe(true);
    expect(businessPlannerTabs.map(getBusinessPlannerPath)).toEqual([
      '/business-dashboard/demand-heatmap',
      '/business-dashboard/saved-sites',
      '/business-dashboard/profile'
    ]);
    expect(getBusinessPlannerTab('/business-dashboard/planner')).toBe('demand-heatmap');
    expect(getBusinessPlannerTab('/business-dashboard/site-analytics')).toBe('demand-heatmap');
    expect(getBusinessPlannerTab('/business-dashboard/unknown')).toBe('demand-heatmap');
    expect(getBusinessPlannerTab('/business-dashboard/saved-sites')).toBe('saved-sites');
    expect(getBusinessPlannerPath('saved-sites')).toBe('/business-dashboard/saved-sites');
    expect(items.some((item) => item.prominent)).toBe(false);
  });
});
