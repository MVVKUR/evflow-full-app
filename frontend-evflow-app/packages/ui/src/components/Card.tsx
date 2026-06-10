import type { ReactNode } from 'react';
import { View } from 'react-native';
import { cardStyles as styles } from '../styles/styles';

type CardProps = {
  children: ReactNode;
};

export function Card({ children }: CardProps) {
  return <View style={styles.card}>{children}</View>;
}
