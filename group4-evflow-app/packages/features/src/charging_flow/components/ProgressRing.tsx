import { View, type ViewStyle } from 'react-native';
import { chargingFlowStyles as styles } from '@evflow/ui';
import type { ReactNode } from 'react';

type ProgressRingProps = {
  progress: number;
  children?: ReactNode;
};

export function ProgressRing({ progress, children }: ProgressRingProps) {
  const ringStyle = {
    backgroundImage: `conic-gradient(#01e0f0 ${progress * 3.6}deg, #dce7eb 0deg)`
  } as unknown as ViewStyle;

  return (
    <View style={[styles.progressRing, ringStyle]}>
      <View style={styles.progressCircle}>
        {children}
      </View>
    </View>
  );
}
