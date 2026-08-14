import { createElement } from 'react';
import type { NavigationItem } from '@evflow/ui';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';
import { buildNavIconSvg, type BusinessNavIconName } from './businessDashboardIcons';

export type BusinessPlannerTabKey = 'demand-heatmap' | 'planner' | 'site-analytics';

export const businessPlannerTabs: readonly BusinessPlannerTabKey[] = [
  'demand-heatmap',
  'planner',
  'site-analytics'
];

export function getBusinessPlannerTab(pathname: string): BusinessPlannerTabKey {
  const tab = pathname.split('/')[2];

  return businessPlannerTabs.includes(tab as BusinessPlannerTabKey) ? tab as BusinessPlannerTabKey : 'planner';
}

export function getBusinessPlannerPath(tab: BusinessPlannerTabKey): string {
  return `/business-dashboard/${tab}`;
}

export function getBusinessPlannerNavigationItems(): NavigationItem[] {
  return [
    makeItem('demand-heatmap', 'Demand Heatmap', 'overview'),
    makeItem('planner', 'Planner', 'planner'),
    makeItem('site-analytics', 'Site Analytics', 'reports')
  ];
}

function makeItem(key: BusinessPlannerTabKey, label: string, iconName: BusinessNavIconName): NavigationItem {
  return {
    key,
    label,
    accessibilityLabel: label,
    icon: ({ color }) => createElement(SvgAssetIcon, { height: 20, svg: buildNavIconSvg(iconName, color), width: 20 })
  };
}
