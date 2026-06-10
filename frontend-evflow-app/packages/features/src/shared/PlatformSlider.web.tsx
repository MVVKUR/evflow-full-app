import { createElement } from 'react';
import type { PlatformSliderProps } from './PlatformSlider';

export function PlatformSlider({
  maximumTrackTintColor = '#dde5e8',
  maximumValue,
  minimumTrackTintColor = '#0bb2b2',
  minimumValue,
  onValueChange,
  step = 1,
  style,
  thumbTintColor = '#0bb2b2',
  value
}: PlatformSliderProps) {
  const percent = ((value - minimumValue) / (maximumValue - minimumValue)) * 100;

  return createElement('input', {
    'aria-label': 'Slider',
    max: maximumValue,
    min: minimumValue,
    onChange: (event: { currentTarget: { value: string } }) => onValueChange(Number(event.currentTarget.value)),
    step,
    type: 'range',
    value,
    style: {
      accentColor: thumbTintColor,
      background: `linear-gradient(to right, ${minimumTrackTintColor} 0%, ${minimumTrackTintColor} ${percent}%, ${maximumTrackTintColor} ${percent}%, ${maximumTrackTintColor} 100%)`,
      borderRadius: 999,
      height: 40,
      marginTop: 8,
      width: '100%',
      ...(typeof style === 'object' && style ? style : {})
    }
  });
}
