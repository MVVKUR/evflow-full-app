import { View } from 'react-native';
import { chargingFlowStyles as styles } from '@evflow/ui';
import type { ReactNode } from 'react';
import Svg, { Circle } from 'react-native-svg';

type ProgressRingProps = {
  progress: number;
  children?: ReactNode;
};

export function ProgressRing({ progress, children }: ProgressRingProps) {
  const size = 240;
  const strokeWidth = 14; // (240 - 212) / 2
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const strokeDashoffset = circumference - (progress / 100) * circumference;

  return (
    <View style={styles.progressRing}>
      <View style={{ position: 'absolute', top: 0, left: 0 }}>
        <Svg width={size} height={size}>
          <Circle
            stroke="#01e0f0"
            fill="none"
            cx={size / 2}
            cy={size / 2}
            r={radius}
            strokeWidth={strokeWidth}
            strokeDasharray={`${circumference} ${circumference}`}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="butt"
            originX={size / 2}
            originY={size / 2}
            rotation="-90"
          />
        </Svg>
      </View>
      <View style={styles.progressCircle}>
        {children}
      </View>
    </View>
  );
}
