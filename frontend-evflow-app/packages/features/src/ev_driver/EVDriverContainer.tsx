import { useMemo } from 'react';
import { Text, useWindowDimensions, View, Platform } from 'react-native';
import { useLocation, useNavigate } from 'react-router';
import { BottomNavigation, evDriverContainerStyles as styles, SideMenu, type NavigationItem } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { DriverAssetIcon } from './components/DriverAssetIcon';
import { DriverMapScreen } from './DriverMapScreen';
import { MockDriverScreen } from './MockDriverScreen';
import { ProfileScreen } from './ProfileScreen';
import { TopUpSuccessScreen, TopUpWalletScreen } from './TopUpWalletScreen';
import { WalletScreen } from './WalletScreen';
import type { DriverTabKey } from './types';

export function EVDriverContainer() {
  const location = useLocation();
  const navigate = useNavigate();
  const { height, width } = useWindowDimensions();
  const insets = useAppSafeAreaInsets();
  const desktop = width >= 768;
  const bottomNavOffset = desktop ? 0 : 84 + insets.bottom;
  const topInset = insets.top;
  const items = useDriverNavigationItems();
  const activeTab = getActiveDriverTab(location.pathname);
  const walletFlow = getWalletFlow(location.pathname);

  return (
    <View style={[styles.shell, styles.viewportShell, { height, maxHeight: height, minHeight: height }]}>
      {desktop ? (
        <View style={[styles.sidebarWrap, { paddingTop: topInset }]}>
          <SideMenu
            activeKey={activeTab}
            bottomContent={<Text style={styles.sidebarNote}>EV Driver Mode</Text>}
            items={items}
            onItemPress={(key) => {
              if (key === 'scan') {
                navigate('/charging-flow/scan');
              } else {
                navigate(getDriverTabPath(key as DriverTabKey));
              }
            }}
            subtitle="Driver"
            title="EV-FLOW"
          />
        </View>
      ) : null}

      <View
        style={[
          styles.content,
          styles.viewportContent,
          activeTab === 'map' && Platform.OS === 'web' && { touchAction: 'none' } as any
        ]}
      >
        {walletFlow === 'topup' ? (
          <TopUpWalletScreen bottomOffset={bottomNavOffset} topInset={topInset} />
        ) : walletFlow === 'success' ? (
          <TopUpSuccessScreen bottomOffset={insets.bottom} topInset={topInset} />
        ) : activeTab === 'map' ? (
          <DriverMapScreen bottomOffset={bottomNavOffset} topInset={topInset} />
        ) : activeTab === 'wallet' ? (
          <WalletScreen bottomInset={insets.bottom} bottomOffset={bottomNavOffset} topInset={topInset} />
        ) : activeTab === 'profile' ? (
          <ProfileScreen bottomOffset={bottomNavOffset} topInset={topInset} />
        ) : (
          <MockDriverScreen tabKey={activeTab} topInset={topInset} />
        )}

        {!desktop && walletFlow !== 'success' ? (
          <View style={[styles.bottomNavWrap, { paddingBottom: insets.bottom }]}>
            <BottomNavigation
              activeKey={activeTab}
              items={items}
              onItemPress={(key) => {
                if (key === 'scan') {
                  navigate('/charging-flow/scan');
                } else {
                  navigate(getDriverTabPath(key as DriverTabKey));
                }
              }}
            />
          </View>
        ) : null}
      </View>
    </View>
  );
}

function getActiveDriverTab(pathname: string): DriverTabKey {
  const tab = pathname.split('/')[2];

  if (tab === 'map' || tab === 'wallet' || tab === 'scan' || tab === 'plan_route' || tab === 'profile') {
    return tab;
  }

  return 'map';
}

function getWalletFlow(pathname: string) {
  if (pathname === '/ev-driver/wallet/topup') {
    return 'topup';
  }

  if (pathname === '/ev-driver/wallet/topup/success') {
    return 'success';
  }

  return null;
}

function getDriverTabPath(tab: DriverTabKey) {
  return `/ev-driver/${tab}`;
}

function useDriverNavigationItems(): NavigationItem[] {
  return useMemo(
    () => [
      {
        key: 'map',
        label: 'Map',
        icon: ({ color }) => <DriverAssetIcon color={color} name="map" />
      },
      {
        key: 'wallet',
        label: 'Wallet',
        icon: ({ color }) => <DriverAssetIcon color={color} name="wallet" />
      },
      {
        key: 'scan',
        label: 'Scan',
        prominent: true,
        icon: ({ color }) => <DriverAssetIcon color={color} name="scan" />
      },
      {
        key: 'plan_route',
        label: 'Plan Route',
        icon: ({ color }) => <DriverAssetIcon color={color} name="plan_route" />
      },
      {
        key: 'profile',
        label: 'Profile',
        icon: ({ color }) => <DriverAssetIcon color={color} name="profile" />
      }
    ],
    []
  );
}
