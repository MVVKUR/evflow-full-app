import { View } from 'react-native';
import { bottomNavigationStyles as styles } from '../styles/styles';
import { NavigationBarButton, type NavigationItem } from './NavigationBarButton';

export { renderIcon, type NavigationItem } from './NavigationBarButton';

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
        return (
          <NavigationBarButton
            active={active}
            item={item}
            key={item.key}
            onPress={onItemPress}
            variant="bottom"
          />
        );
      })}
    </View>
  );
}
