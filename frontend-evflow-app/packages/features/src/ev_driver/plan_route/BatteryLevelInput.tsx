import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

type BatteryLevelInputProps = {
  value: number;
  inputText: string;
  onChangeText: (text: string) => void;
  onQuickSelect: (val: number) => void;
  estimatedRangeKm?: number | null;
};

const quickValues = [25, 50, 75, 100];

export function BatteryLevelInput({
  value,
  inputText,
  onChangeText,
  onQuickSelect,
  estimatedRangeKm
}: BatteryLevelInputProps) {
  return (
    <View style={styles.card}>
      <Text style={styles.sectionHeader}>CURRENT BATTERY LEVEL</Text>

      <View style={styles.topRow}>
        <View style={styles.batteryIconWrap}>
          <View style={styles.batteryBody}>
            <View style={[styles.batteryFill, { width: `${Math.max(5, Math.min(100, value))}%` }]} />
          </View>
          <View style={styles.batteryTip} />
        </View>

        <View style={styles.valueWrap}>
          <View style={styles.inputRow}>
            <TextInput
              style={styles.textInput}
              keyboardType="numeric"
              value={inputText}
              onChangeText={onChangeText}
              placeholder="72"
              placeholderTextColor="#94A3B8"
              maxLength={5}
            />
            <Text style={styles.percentSymbol}>%</Text>
          </View>
          {estimatedRangeKm != null && estimatedRangeKm > 0 ? (
            <Text style={styles.rangeSub}>Est. Range: {Math.round(estimatedRangeKm)} km</Text>
          ) : (
            <Text style={styles.rangeSub}>Est. Range: -- km</Text>
          )}
        </View>
      </View>

      <View style={styles.quickRow}>
        {quickValues.map((qv) => {
          const isSelected = value === qv && (inputText === String(qv) || inputText === `${qv}%`);
          return (
            <Pressable
              key={qv}
              style={[styles.quickButton, isSelected && styles.quickButtonSelected]}
              onPress={() => onQuickSelect(qv)}
            >
              <Text style={[styles.quickText, isSelected && styles.quickTextSelected]}>
                {qv}%
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
  sectionHeader: {
    fontSize: 11,
    fontWeight: '700',
    color: '#64748B',
    letterSpacing: 0.8,
    marginBottom: 12,
    textTransform: 'uppercase',
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  batteryIconWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    marginRight: 16,
  },
  batteryBody: {
    width: 44,
    height: 24,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: '#0F172A',
    padding: 2,
    justifyContent: 'center',
  },
  batteryFill: {
    height: '100%',
    backgroundColor: '#10B981',
    borderRadius: 3,
  },
  batteryTip: {
    width: 3,
    height: 10,
    backgroundColor: '#0F172A',
    borderTopRightRadius: 2,
    borderBottomRightRadius: 2,
  },
  valueWrap: {
    flex: 1,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  textInput: {
    fontSize: 32,
    fontWeight: '800',
    color: '#0F172A',
    padding: 0,
    margin: 0,
    minWidth: 48,
  },
  percentSymbol: {
    fontSize: 24,
    fontWeight: '700',
    color: '#0F172A',
    marginLeft: 2,
  },
  rangeSub: {
    fontSize: 13,
    color: '#64748B',
    marginTop: 2,
    fontWeight: '500',
  },
  quickRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  quickButton: {
    flex: 1,
    paddingVertical: 10,
    backgroundColor: '#F1F5F9',
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  quickButtonSelected: {
    backgroundColor: '#00696F',
  },
  quickText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#334155',
  },
  quickTextSelected: {
    color: '#FFFFFF',
  },
});
