import { Pressable, ScrollView, Text, View } from 'react-native';
import { colors, profileSelectionStyles as styles } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';
import { RoleAssetIcon } from './components/RoleAssetIcon';
import { rightArrowIcon } from './components/profileSelectionIcons';
import type { UserRole } from './types';

type ProfileSelectionScreenProps = {
  selectedRole: UserRole;
  onBack: () => void;
  onContinue: () => void;
  onSelectRole: (role: UserRole) => void;
};

export function ProfileSelectionScreen({ selectedRole, onBack, onContinue, onSelectRole }: ProfileSelectionScreenProps) {
  const insets = useAppSafeAreaInsets();

  return (
    <View style={styles.page}>
      <View style={styles.contentShell}>
        <View style={[styles.header, { paddingTop: insets.top }]}>
          <Pressable accessibilityLabel="Back" accessibilityRole="button" onPress={onBack} style={styles.backButton}>
            <SvgAssetIcon color="#191C1D" height={12} name="leftChevron" width={8} />
          </Pressable>
          <Text style={styles.brand}>EV-FLOW</Text>
          <View style={styles.headerSpacer} />
        </View>

        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: 120 + insets.bottom }]}>
          <Text style={styles.title}>Complete Your Profile</Text>
          <Text style={styles.subtitle}>
            Choose an account type to customize your driving or planning experience.
          </Text>

          <RoleCard
            description="Find the nearest charging stations (SPKLU), filter by connector type (CCS2/AC Type 2), plan your travel route, and monitor real-time charging."
            role="driver"
            selected={selectedRole === 'driver'}
            title="EV User (Driver)"
            onPress={() => onSelectRole('driver')}
          />
          <RoleCard
            description="Access the VoltGrid dashboard, analyze BPS spatial data, map demand hotspots, and optimize the location of new SPKLUs in Jakarta."
            role="operator"
            selected={selectedRole === 'operator'}
            title="Business Planner"
            onPress={() => onSelectRole('operator')}
          />
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: 20 + insets.bottom }]}>
          <Pressable accessibilityRole="button" onPress={onContinue} style={styles.continueButton}>
            <Text style={styles.continueText}>Continue to register</Text>
            <SvgAssetIcon height={16} name="rightArrow" svg={rightArrowIcon} width={16} />
          </Pressable>
        </View>
      </View>
    </View>
  );
}

type RoleCardProps = {
  title: string;
  description: string;
  role: UserRole;
  selected: boolean;
  onPress: () => void;
};

function RoleCard({ title, description, role, selected, onPress }: RoleCardProps) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={[styles.roleCard, selected && styles.selectedRoleCard]}
    >
      <View style={[styles.roleIcon, selected && styles.selectedRoleIcon]}>
        <RoleAssetIcon color={selected ? colors.text : '#3d494b'} role={role} />
      </View>

      <View style={styles.roleText}>
        <Text style={styles.roleTitle}>{title}</Text>
        <Text style={styles.roleDescription}>{description}</Text>
      </View>

      <View style={[styles.radio, selected && styles.selectedRadio]}>
        {selected ? <Text style={styles.radioCheck}>✓</Text> : null}
      </View>
    </Pressable>
  );
}
