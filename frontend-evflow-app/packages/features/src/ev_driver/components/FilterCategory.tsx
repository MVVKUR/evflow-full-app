import { Pressable, Text, View } from 'react-native';
import { filterCategoryStyles as styles } from '@evflow/ui';
import { SvgAssetIcon } from '../../shared/SvgAssetIcon';

export type FilterOption = {
  key: string;
  label: string;
  description?: string;
};

type FilterCategoryProps = {
  title: string;
  options: FilterOption[];
  selectedKeys: string[];
  variant?: 'pill' | 'card';
  onToggle: (key: string) => void;
};

export function FilterCategory({ title, options, selectedKeys, variant = 'pill', onToggle }: FilterCategoryProps) {
  return (
    <View style={styles.category}>
      <Text style={styles.title}>{title}</Text>
      <View style={variant === 'card' ? styles.cardOptions : styles.pillOptions}>
        {options.map((option) => {
          const selected = selectedKeys.includes(option.key);

          return (
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ selected }}
              key={option.key}
              onPress={() => onToggle(option.key)}
              style={[variant === 'card' ? styles.cardOption : styles.pillOption, selected && styles.selectedOption]}
            >
              <Text style={[variant === 'card' ? styles.cardLabel : styles.pillLabel, selected && styles.selectedLabel]}>
                {option.label}
              </Text>
              {variant === 'card' && selected ? (
                <View style={styles.cardTickIcon}>
                  <SvgAssetIcon color="#005F64" height={12} name="tick" width={12} />
                </View>
              ) : null}
              {option.description ? (
                <Text style={[styles.description, selected && styles.selectedDescription]}>{option.description}</Text>
              ) : null}
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
