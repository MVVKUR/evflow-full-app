import { Pressable, Text, View } from 'react-native';
import { chargingFlowStyles as styles } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../../shared/useAppSafeAreaInsets';
import { ChargingFlowIcon, type ChargingIconName } from './ChargingFlowIcon';

type ChargingFlowHeaderProps = {
  title: string;
  onBack: () => void;
  rightIconName?: ChargingIconName;
  rightIconColor?: string;
  rightIconSize?: number;
  onRightPress?: () => void;
};

export function ChargingFlowHeader({
  title,
  onBack,
  rightIconName,
  rightIconColor,
  rightIconSize = 20,
  onRightPress
}: ChargingFlowHeaderProps) {
  const insets = useAppSafeAreaInsets();
  const rightContent = rightIconName ? (
    <ChargingFlowIcon name={rightIconName} size={rightIconSize} color={rightIconColor} />
  ) : null;

  return (
    <View style={[styles.header, { paddingLeft: 20 + insets.left, paddingRight: 20 + insets.right, paddingTop: insets.top }]}>
      <Pressable accessibilityLabel="Back" accessibilityRole="button" onPress={onBack} style={styles.backButton}>
        <ChargingFlowIcon name="leftArrow" size={24} color="#005F64" />
      </Pressable>
      <Text numberOfLines={1} style={styles.headerTitle}>
        {title}
      </Text>
      {onRightPress && rightContent ? (
        <Pressable accessibilityRole="button" onPress={onRightPress} style={styles.headerRight}>
          {rightContent}
        </Pressable>
      ) : (
        <View style={styles.headerRight}>{rightContent}</View>
      )}
    </View>
  );
}
