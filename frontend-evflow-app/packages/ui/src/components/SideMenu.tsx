import type { ReactNode } from 'react';
import { Text, View } from 'react-native';
import { NavigationBarButton, type NavigationItem } from './NavigationBarButton';
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
            return (
              <NavigationBarButton
                active={active}
                item={item}
                key={item.key}
                onPress={onItemPress}
                variant="side"
              />
            );
          })}
        </View>
      </View>

      {bottomContent ? <View style={styles.bottom}>{bottomContent}</View> : null}
    </View>
  );
}
