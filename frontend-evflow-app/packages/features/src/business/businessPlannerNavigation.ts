import { createElement } from 'react';
import type { NavigationItem } from '@evflow/ui';
import { DriverAssetIcon } from '../ev_driver/components/DriverAssetIcon';

export type BusinessPlannerTabKey = 'demand-heatmap' | 'profile';

export const businessPlannerTabs: readonly BusinessPlannerTabKey[] = [
  'demand-heatmap',
  'profile'
];

export function getBusinessPlannerTab(pathname: string): BusinessPlannerTabKey {
  const tab = pathname.split('/')[2];

  return businessPlannerTabs.includes(tab as BusinessPlannerTabKey)
    ? tab as BusinessPlannerTabKey
    : 'demand-heatmap';
}

export function getBusinessPlannerPath(tab: BusinessPlannerTabKey): string {
  return `/business-dashboard/${tab}`;
}

export function getBusinessPlannerNavigationItems(): NavigationItem[] {
  return [
    makeItem('demand-heatmap', 'Demand Heatmap', 'map'),
    makeItem('profile', 'Profile', 'profile')
  ];
}

function makeItem(key: BusinessPlannerTabKey, label: string, iconName: 'map' | 'profile'): NavigationItem {
  return {
    key,
    label,
    accessibilityLabel: label,
    icon: ({ color }) => createElement(DriverAssetIcon, { color, name: iconName })
  };
}
