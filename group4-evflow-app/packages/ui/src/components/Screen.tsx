import type { ReactNode } from 'react';
import { ScrollView } from 'react-native';
import { screenStyles as styles } from '../styles/styles';

type ScreenProps = {
  children: ReactNode;
};

export function Screen({ children }: ScreenProps) {
  return <ScrollView contentContainerStyle={styles.content}>{children}</ScrollView>;
}
