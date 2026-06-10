import Slider from '@react-native-community/slider';
import type { StyleProp, ViewStyle } from 'react-native';

export type PlatformSliderProps = {
  maximumTrackTintColor?: string;
  maximumValue: number;
  minimumTrackTintColor?: string;
  minimumValue: number;
  onValueChange: (value: number) => void;
  step?: number;
  style?: StyleProp<ViewStyle>;
  thumbTintColor?: string;
  value: number;
};

export function PlatformSlider(props: PlatformSliderProps) {
  return <Slider {...props} />;
}
