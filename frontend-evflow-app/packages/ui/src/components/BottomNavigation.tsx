import type { ReactNode } from 'react';
import { Pressable, Text, View } from 'react-native';
import { colors } from '../theme/colors';
import { bottomNavigationStyles as styles } from '../styles/styles';

type NavigationIconOptions = {
  active: boolean;
  color: string;
};

// NonNullable so the optional `activeIcon?` isn't redundantly `... | undefined | undefined`.
type NavigationIcon = NonNullable<ReactNode> | ((options: NavigationIconOptions) => ReactNode);

export type NavigationItem = {
  key: string;
  label: string;
  icon: NavigationIcon;
  activeIcon?: NavigationIcon;
  accessibilityLabel?: string;
  prominent?: boolean;
};

type BottomNavigationProps = {
  items: NavigationItem[];
  activeKey: string;
  onItemPress?: (key: string) => void;
};

export function BottomNavigation({ items, activeKey, onItemPress }: BottomNavigationProps) {
  return (
    <View style={styles.container}>
      {items.map((item) => {
        const active = item.key === activeKey;
        const icon = renderIcon(item, active);

        if (item.prominent) {
          return (
            <Pressable
              accessibilityLabel={item.accessibilityLabel ?? item.label}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              key={item.key}
              onPress={() => onItemPress?.(item.key)}
              style={styles.prominentItem}
            >
              <View style={styles.prominentIcon}>{icon}</View>
              <Text style={[styles.label, active && styles.activeLabel]} numberOfLines={1}>
                {item.label}
              </Text>
            </Pressable>
          );
        }

        return (
          <Pressable
            accessibilityLabel={item.accessibilityLabel ?? item.label}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            key={item.key}
            onPress={() => onItemPress?.(item.key)}
            style={[styles.item, active && styles.activeItem]}
          >
            <View style={styles.icon}>{icon}</View>
            <Text style={[styles.label, active && styles.activeLabel]} numberOfLines={1}>
              {item.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function renderIcon(item: NavigationItem, active: boolean) {
  const icon = active && item.activeIcon ? item.activeIcon : item.icon;
  const color = active ? colors.text : colors.mutedText;

  return typeof icon === 'function' ? icon({ active, color }) : icon;
}
