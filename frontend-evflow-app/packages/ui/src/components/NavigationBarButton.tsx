import { Pressable, Text, View } from 'react-native';
import type { ReactNode } from 'react';
import { bottomNavigationStyles as bottomStyles, sideMenuStyles as sideStyles } from '../styles/styles';

type NavigationIconOptions = {
  active: boolean;
  color: string;
};

type NavigationIcon = NonNullable<ReactNode> | ((options: NavigationIconOptions) => ReactNode);

export type NavigationItem = {
  key: string;
  label: string;
  icon: NavigationIcon;
  activeIcon?: NavigationIcon;
  accessibilityLabel?: string;
  disabled?: boolean;
  prominent?: boolean;
};

export function renderIcon(item: NavigationItem, active: boolean) {
  const icon = active && item.activeIcon ? item.activeIcon : item.icon;
  const color = active ? '#191C1E' : '#657275';

  return typeof icon === 'function' ? icon({ active, color }) : icon;
}

export type NavigationBarButtonProps = {
  item: NavigationItem;
  active: boolean;
  variant: 'bottom' | 'side';
  onPress?: (key: string) => void;
};

/**
 * One navigation control for both compact bottom bars and desktop side menus.
 * `prominent` is deliberately only rendered in the compact variant, so a
 * centre action (such as Driver Scan) never distorts the desktop menu.
 */
export function NavigationBarButton({ item, active, variant, onPress }: NavigationBarButtonProps) {
  const icon = renderIcon(item, active);
  const disabled = Boolean(item.disabled);
  const useProminentStyle = variant === 'bottom' && item.prominent;

  if (useProminentStyle) {
    return (
      <Pressable
        accessibilityLabel={item.accessibilityLabel ?? item.label}
        accessibilityRole="tab"
        accessibilityState={{ disabled, selected: active }}
        disabled={disabled}
        onPress={() => onPress?.(item.key)}
        style={[bottomStyles.prominentItem, disabled && bottomStyles.disabledItem]}
      >
        <View style={bottomStyles.prominentIcon}>{icon}</View>
        <Text style={[bottomStyles.label, active && bottomStyles.activeLabel]} numberOfLines={1}>{item.label}</Text>
      </Pressable>
    );
  }

  const styles = variant === 'bottom' ? bottomStyles : sideStyles;
  return (
    <Pressable
      accessibilityLabel={item.accessibilityLabel ?? item.label}
      accessibilityRole="tab"
      accessibilityState={{ disabled, selected: active }}
      disabled={disabled}
      onPress={() => onPress?.(item.key)}
      style={[styles.item, active && styles.activeItem, disabled && bottomStyles.disabledItem]}
    >
      <View style={styles.icon}>{icon}</View>
      <Text style={[styles.label, active && styles.activeLabel]} numberOfLines={1}>{item.label}</Text>
    </Pressable>
  );
}
