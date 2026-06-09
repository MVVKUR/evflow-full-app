import type { ReactNode } from 'react';
import { Pressable, Text } from 'react-native';
import { buttonStyles as styles } from '../styles/styles';

type ButtonProps = {
  children: ReactNode;
  onPress?: () => void;
};

export function Button({ children, onPress }: ButtonProps) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.button}>
      <Text style={styles.label}>{children}</Text>
    </Pressable>
  );
}
