import { useMemo, useState } from 'react';
import { FlatList, Modal, Pressable, Text, View } from 'react-native';
import { registrationScreenStyles as styles } from '@evflow/ui';

export type ModelPickerOption = {
  label: string;
  value: string;
};

type ModelPickerProps = {
  onValueChange: (value: string) => void;
  options: ModelPickerOption[];
  placeholderLabel: string;
  selectedValue: string;
};

export function ModelPicker({ onValueChange, options, placeholderLabel, selectedValue }: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const selectedOption = useMemo(
    () => options.find((option) => option.value === selectedValue),
    [options, selectedValue]
  );

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen(true)}
        style={styles.selectToggle}
      >
        <Text numberOfLines={1} style={[styles.selectText, !selectedOption && styles.placeholderText]}>
          {selectedOption?.label ?? placeholderLabel}
        </Text>
        <Text style={styles.chevron}>⌄</Text>
      </Pressable>

      <Modal animationType="fade" transparent visible={open} onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.selectBackdrop} onPress={() => setOpen(false)}>
          <View style={styles.selectModal}>
            <Text style={styles.selectModalTitle}>{placeholderLabel}</Text>
            <FlatList
              data={options}
              keyExtractor={(option) => option.value}
              showsVerticalScrollIndicator
              renderItem={({ item }) => {
                const selected = item.value === selectedValue;

                return (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityState={{ selected }}
                    onPress={() => {
                      onValueChange(item.value);
                      setOpen(false);
                    }}
                    style={[styles.selectOption, selected && styles.selectedSelectOption]}
                  >
                    <Text numberOfLines={2} style={styles.selectOptionText}>
                      {item.label}
                    </Text>
                  </Pressable>
                );
              }}
            />
          </View>
        </Pressable>
      </Modal>
    </>
  );
}
