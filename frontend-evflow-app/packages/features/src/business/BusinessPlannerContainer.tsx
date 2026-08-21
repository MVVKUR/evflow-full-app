import { useMemo } from 'react';
import { Text, useWindowDimensions, View } from 'react-native';
import { useLocation, useNavigate } from 'react-router';
import { BottomNavigation, evDriverContainerStyles as containerStyles, SideMenu } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { ProfileScreen } from '../ev_driver/ProfileScreen';
import { DemandHeatmapScreen } from './DemandHeatmapScreen';
import { SavedSitesScreen } from './saved-sites/SavedSitesScreen';
import { getBusinessPlannerNavigationItems, getBusinessPlannerPath, getBusinessPlannerTab } from './businessPlannerNavigation';

/**
 * Uses the same responsive navigation composition as EVDriverContainer:
 * sidebar on desktop and a bottom tab bar on mobile. The latter has no raised
 * action because none of the Business Planner tabs is marked prominent.
 */
export function BusinessPlannerContainer() {
  const { height, width } = useWindowDimensions();
  const insets = useAppSafeAreaInsets();
  const location = useLocation();
  const navigate = useNavigate();
  const desktop = width >= 768;
  const items = useMemo(() => getBusinessPlannerNavigationItems(), []);
  const activeTab = getBusinessPlannerTab(location.pathname);
  const bottomOffset = desktop ? 0 : 84 + insets.bottom;

  return (
    <View style={[containerStyles.shell, containerStyles.viewportShell, { height, maxHeight: height, minHeight: height }]}>
      {desktop ? (
        <View style={[containerStyles.sidebarWrap, { paddingTop: insets.top }]}>
          <SideMenu
            activeKey={activeTab}
            bottomContent={<Text style={containerStyles.sidebarNote}>Business Planner</Text>}
            items={items}
            onItemPress={(key) => navigate(getBusinessPlannerPath(key as typeof activeTab))}
            subtitle="Planning"
            title="EV-FLOW"
          />
        </View>
      ) : null}

      <View style={[containerStyles.content, containerStyles.viewportContent]}>
        {activeTab === 'demand-heatmap' && <DemandHeatmapScreen bottomOffset={bottomOffset} topInset={insets.top} />}
        {activeTab === 'saved-sites' && <SavedSitesScreen bottomOffset={bottomOffset} topInset={insets.top} />}
        {activeTab === 'profile' && <ProfileScreen bottomOffset={bottomOffset} topInset={insets.top} />}

        {!desktop ? (
          <View style={[containerStyles.bottomNavWrap, { paddingBottom: insets.bottom }]}>
            <BottomNavigation
              activeKey={activeTab}
              items={items}
              onItemPress={(key) => navigate(getBusinessPlannerPath(key as typeof activeTab))}
            />
          </View>
        ) : null}
      </View>
    </View>
  );
}
