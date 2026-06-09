import { createElement } from 'react';
import type { ModelPickerOption } from './ModelPicker';

type ModelPickerProps = {
  onValueChange: (value: string) => void;
  options: ModelPickerOption[];
  placeholderLabel: string;
  selectedValue: string;
};

export function ModelPicker({ onValueChange, options, placeholderLabel, selectedValue }: ModelPickerProps) {
  return createElement(
    'select',
    {
      'aria-label': 'Select your car',
      onChange: (event: { currentTarget: { value: string } }) => onValueChange(event.currentTarget.value),
      value: selectedValue,
      style: {
        appearance: 'none',
        background: 'transparent',
        border: 0,
        color: selectedValue ? '#1f2529' : '#9aa4a9',
        flex: 1,
        font: 'inherit',
        minHeight: 48,
        outline: 'none',
        width: '100%'
      }
    },
    [
      createElement('option', { key: '', value: '' }, placeholderLabel),
      ...options.map((option) => createElement('option', { key: option.value, value: option.value }, option.label))
    ]
  );
}
