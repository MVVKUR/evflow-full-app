import type { ReactNode } from 'react';
import { Pressable, Text, View } from 'react-native';
import { renderIcon, type NavigationItem } from './BottomNavigation';
import { sideMenuStyles as styles } from '../styles/styles';

type SideMenuProps = {
  items: NavigationItem[];
  activeKey: string;
  onItemPress?: (key: string) => void;
  title?: string;
  subtitle?: string;
  topContent?: ReactNode;
  bottomContent?: ReactNode;
};

export function SideMenu({
  items,
  activeKey,
  onItemPress,
  title,
  subtitle,
  topContent,
  bottomContent
}: SideMenuProps) {
  return (
    <View style={styles.container}>
      <View style={styles.top}>
        {(title || subtitle) && (
          <View style={styles.brand}>
            {title ? <Text style={styles.title}>{title}</Text> : null}
            {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
          </View>
        )}

        {topContent ? <View style={styles.customContainer}>{topContent}</View> : null}

        <View style={styles.items}>
          {items.map((item) => {
            const active = item.key === activeKey;
            const icon = renderIcon(item, active);

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
      </View>

      {bottomContent ? <View style={styles.bottom}>{bottomContent}</View> : null}
    </View>
  );
}
