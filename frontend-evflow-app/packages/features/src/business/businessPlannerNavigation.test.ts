import { describe, expect, it } from 'vitest';
import { businessPlannerTabs, getBusinessPlannerNavigationItems, getBusinessPlannerPath, getBusinessPlannerTab } from './businessPlannerNavigation';

describe('Business Planner navigation', () => {
  it('defines exactly the three tabs needed by the demand and feasibility epics', () => {
    expect(businessPlannerTabs).toEqual(['demand-heatmap', 'planner', 'site-analytics']);
    expect(getBusinessPlannerNavigationItems().map((item) => item.label)).toEqual([
      'Demand Heatmap',
      'Planner',
      'Site Analytics'
    ]);
  });

  it('provides a route for every tab and defaults unknown Business Dashboard paths to Planner', () => {
    const items = getBusinessPlannerNavigationItems();

    expect(items.every((item) => !item.disabled)).toBe(true);
    expect(businessPlannerTabs.map(getBusinessPlannerPath)).toEqual([
      '/business-dashboard/demand-heatmap',
      '/business-dashboard/planner',
      '/business-dashboard/site-analytics'
    ]);
    expect(getBusinessPlannerTab('/business-dashboard/unknown')).toBe('planner');
    expect(items.some((item) => item.prominent)).toBe(false);
  });
});
