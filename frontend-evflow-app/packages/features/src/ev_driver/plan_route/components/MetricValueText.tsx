import { Text, type StyleProp, type TextStyle } from 'react-native';

// Splits a formatted metric string ("12 km", "8.4 kWh", "1h 05m", "54%") into
// number runs and unit/text runs so numbers can be the dominant typography
// while units stay small.
const numberRunPattern = /(\d+(?:[.,]\d+)?)/;

export function splitMetricValue(value: string): Array<{ text: string; isNumber: boolean }> {
  return value
    .split(numberRunPattern)
    .filter((part) => part.length > 0)
    .map((part) => ({ text: part, isNumber: /^\d/.test(part) }));
}

type MetricValueTextProps = {
  value: string;
  numberStyle: StyleProp<TextStyle>;
  unitStyle: StyleProp<TextStyle>;
};

// Renders a formatted metric value with hero numbers and de-emphasised units.
// The full string stays one accessible label, so screen readers announce the
// value exactly as they did before the visual split.
export function MetricValueText({ value, numberStyle, unitStyle }: MetricValueTextProps) {
  return (
    <Text accessibilityLabel={value} style={numberStyle}>
      {splitMetricValue(value).map((part, index) => (
        <Text key={`${index}-${part.text}`} style={part.isNumber ? numberStyle : unitStyle}>{part.text}</Text>
      ))}
    </Text>
  );
}
