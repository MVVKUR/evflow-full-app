import { describe, expect, it } from 'vitest';
import { businessPlannerTabs, getBusinessPlannerNavigationItems, getBusinessPlannerPath, getBusinessPlannerTab } from './businessPlannerNavigation';

describe('Business Planner navigation', () => {
  it('defines only the Demand Heatmap and Profile tabs', () => {
    expect(businessPlannerTabs).toEqual(['demand-heatmap', 'profile']);
    expect(getBusinessPlannerNavigationItems().map((item) => item.label)).toEqual([
      'Demand Heatmap',
      'Profile'
    ]);
  });

  it('provides a route for every tab and defaults unknown paths to Demand Heatmap', () => {
    const items = getBusinessPlannerNavigationItems();

    expect(items.every((item) => !item.disabled)).toBe(true);
    expect(businessPlannerTabs.map(getBusinessPlannerPath)).toEqual([
      '/business-dashboard/demand-heatmap',
      '/business-dashboard/profile'
    ]);
    expect(getBusinessPlannerTab('/business-dashboard/planner')).toBe('demand-heatmap');
    expect(getBusinessPlannerTab('/business-dashboard/site-analytics')).toBe('demand-heatmap');
    expect(getBusinessPlannerTab('/business-dashboard/unknown')).toBe('demand-heatmap');
    expect(items.some((item) => item.prominent)).toBe(false);
  });
});
