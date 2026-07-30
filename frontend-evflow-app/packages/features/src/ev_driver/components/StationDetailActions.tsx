import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { StationAvailability } from '../station-status/aggregateConnectorStatuses';

type StationDetailActionsProps = {
  availability: StationAvailability;
  onBack: () => void;
  onChargeHere?: () => void;
};

export function StationDetailActions({ availability, onBack, onChargeHere }: StationDetailActionsProps) {
  const canCharge = availability.state === 'available' || (availability.state === 'occupied' && Boolean(availability.earliestEstimate));
  const primaryLabel = availability.state === 'occupied' && availability.earliestEstimate
    ? `Wait Here (~${availability.earliestEstimate.minutes} min)`
    : 'Charge Here Now';
  return (
    <View style={actionStyles.actions}>
      <Text style={actionStyles.prompt}>What would you like to do?</Text>
      {canCharge && onChargeHere ? (
        <Pressable accessibilityLabel={primaryLabel} accessibilityRole="button" onPress={onChargeHere} style={actionStyles.primary}>
          <Text style={actionStyles.primaryText}>◷  {primaryLabel}</Text>
        </Pressable>
      ) : null}
      <Pressable accessibilityLabel="Back to nearby stations" accessibilityRole="button" onPress={onBack} style={actionStyles.secondary}>
        <Text style={actionStyles.secondaryText}>⌖  Back to Nearby Stations</Text>
      </Pressable>
    </View>
  );
}

const actionStyles = StyleSheet.create({
  actions: { gap: 10, marginTop: 8 },
  prompt: { color: '#687378', fontSize: 12, lineHeight: 17, marginBottom: 1 },
  primary: { alignItems: 'center', backgroundColor: '#007A80', borderRadius: 11, justifyContent: 'center', minHeight: 49, paddingHorizontal: 18 },
  primaryText: { color: '#FFFFFF', fontSize: 14, fontWeight: '900' },
  secondary: { alignItems: 'center', backgroundColor: '#FFFFFF', borderColor: '#007A80', borderRadius: 11, borderWidth: 1.5, justifyContent: 'center', minHeight: 49, paddingHorizontal: 18 },
  secondaryText: { color: '#005F64', fontSize: 14, fontWeight: '900' }
});
