import { createElement } from 'react';
import type { NavigationItem } from '@evflow/ui';
import { DriverAssetIcon } from '../ev_driver/components/DriverAssetIcon';
import { BusinessPlannerIcon } from './BusinessPlannerIcon';

export type BusinessPlannerTabKey = 'demand-heatmap' | 'saved-sites' | 'profile';

export const businessPlannerTabs: readonly BusinessPlannerTabKey[] = [
  'demand-heatmap',
  'saved-sites',
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
    makeItem('demand-heatmap', 'Heatmap', 'map'),
    {
      key: 'saved-sites', label: 'Saved Sites', accessibilityLabel: 'Saved Sites',
      icon: ({ color }) => createElement(BusinessPlannerIcon, { color, name: 'bookmark' })
    },
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
