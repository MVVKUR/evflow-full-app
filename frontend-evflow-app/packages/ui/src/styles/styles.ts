import { StyleSheet } from 'react-native';
import { colors } from '../theme/colors';

export const layout = {
  authPageMaxWidth: 420,
  sidebarWidth: 256
} as const;

export const fontSizes = {
  micro: 8,
  eyebrow: 10,
  tiny: 11,
  caption: 12,
  label: 13,
  control: 14,
  body: 15,
  bodyLarge: 16,
  heading: 18,
  icon: 20,
  titleSmall: 21,
  titleMedium: 22,
  title: 23,
  brand: 25,
  display: 28,
  logo: 30,
  iconLarge: 32
} as const;

export const buttonStyles = StyleSheet.create({
  button: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 8,
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: 16
  },
  label: {
    color: colors.text,
    fontSize: fontSizes.body,
    fontWeight: '700'
  }
});

export const cardStyles = StyleSheet.create({
  card: {
    backgroundColor: colors.white,
    borderColor: '#dbe4ef',
    borderRadius: 8,
    borderWidth: 1,
    padding: 16
  }
});

export const screenStyles = StyleSheet.create({
  content: {
    gap: 16,
    marginHorizontal: 'auto',
    maxWidth: 960,
    padding: 20,
    width: '100%'
  }
});

export const filterPillStyles = StyleSheet.create({
  pill: {
    borderColor: '#94a3b8',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8
  },
  selected: {
    backgroundColor: colors.primary,
    borderColor: colors.primary
  },
  label: {
    color: colors.text,
    fontSize: fontSizes.control,
    fontWeight: '600'
  },
  selectedLabel: {
    color: colors.text
  }
});

export const bottomNavigationStyles = StyleSheet.create({
  container: {
    alignItems: 'center',
    backgroundColor: colors.background,
    borderTopColor: colors.border,
    borderTopWidth: 1,
    flexDirection: 'row',
    gap: 8,
    minHeight: 84,
    paddingBottom: 10,
    paddingHorizontal: 16,
    paddingTop: 8
  },
  item: {
    alignItems: 'center',
    borderRadius: 24,
    flex: 1,
    gap: 4,
    justifyContent: 'center',
    minHeight: 56,
    paddingHorizontal: 8
  },
  activeItem: {
    backgroundColor: colors.primary
  },
  prominentItem: {
    alignItems: 'center',
    flex: 1,
    gap: 2,
    justifyContent: 'center',
    minHeight: 56
  },
  prominentIcon: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderColor: colors.background,
    borderRadius: 30,
    borderWidth: 4,
    height: 60,
    justifyContent: 'center',
    marginTop: -34,
    width: 60
  },
  icon: {
    alignItems: 'center',
    height: 22,
    justifyContent: 'center',
    width: 22
  },
  label: {
    color: colors.mutedText,
    fontSize: fontSizes.caption,
    fontWeight: '700',
    lineHeight: 16,
    textAlign: 'center'
  },
  activeLabel: {
    color: colors.text
  }
});

export const sideMenuStyles = StyleSheet.create({
  container: {
    backgroundColor: colors.background,
    borderRightColor: colors.border,
    borderRightWidth: 1,
    flexBasis: layout.sidebarWidth,
    flexGrow: 0,
    flexShrink: 0,
    justifyContent: 'space-between',
    minHeight: '100%',
    padding: 18,
    width: layout.sidebarWidth
  },
  top: {
    gap: 28
  },
  brand: {
    gap: 2,
    paddingHorizontal: 8,
    paddingTop: 8
  },
  title: {
    color: colors.text,
    fontSize: fontSizes.titleMedium,
    fontWeight: '800',
    lineHeight: 28
  },
  subtitle: {
    color: colors.mutedText,
    fontSize: fontSizes.label,
    fontWeight: '700',
    letterSpacing: 0,
    lineHeight: 18
  },
  customContainer: {
    paddingHorizontal: 8
  },
  items: {
    gap: 8
  },
  item: {
    alignItems: 'center',
    borderRadius: 8,
    flexDirection: 'row',
    gap: 12,
    minHeight: 42,
    paddingHorizontal: 14,
    paddingVertical: 10
  },
  activeItem: {
    backgroundColor: colors.primary
  },
  icon: {
    alignItems: 'center',
    height: 22,
    justifyContent: 'center',
    width: 22
  },
  label: {
    color: colors.mutedText,
    flex: 1,
    fontSize: fontSizes.label,
    fontWeight: '700',
    letterSpacing: 0,
    lineHeight: 18
  },
  activeLabel: {
    color: colors.text
  },
  bottom: {
    borderTopColor: colors.border,
    borderTopWidth: 1,
    paddingTop: 18
  }
});

export const leafletMapStyles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#d7dbdc'
  },
  map: {
    flex: 1,
    backgroundColor: 'transparent'
  }
});

export const mapViewStyles = StyleSheet.create({
  nativeContainer: {
    backgroundColor: '#dbeafe',
    borderColor: '#93c5fd',
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 220,
    padding: 16
  },
  nativeTitle: {
    color: '#1e3a8a',
    fontSize: fontSizes.heading,
    fontWeight: '700'
  },
  nativeBody: {
    color: '#1e40af',
    marginTop: 8
  },
  webContainer: {
    backgroundColor: '#ecfeff',
    borderColor: '#67e8f9',
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 220,
    padding: 16
  },
  webTitle: {
    color: '#155e75',
    fontSize: fontSizes.heading,
    fontWeight: '700',
    marginBottom: 8
  },
  webMarker: {
    color: '#164e63',
    marginTop: 4
  }
});

export const loginScreenStyles = StyleSheet.create({
  page: {
    alignItems: 'center',
    backgroundColor: colors.background,
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: 30,
    paddingVertical: 36
  },
  spacer: {
    flex: 1
  },
  top: {
    alignItems: 'center',
    minHeight: 132,
    width: '100%'
  },
  signupText: {
    color: '#1f2529',
    fontSize: fontSizes.control,
    lineHeight: 20,
    marginTop: 24,
    textAlign: 'center'
  },
  signupLink: {
    color: colors.text,
    fontWeight: '700'
  },
  markerCredentialsInfo: {
    color: '#1f2529',
    fontSize: fontSizes.control,
    lineHeight: 20,
    marginTop: 24,
    textAlign: 'justify'
  },
  content: {
    alignItems: 'center',
    maxWidth: layout.authPageMaxWidth,
    width: '100%'
  },
  logoCircle: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 32,
    height: 64,
    justifyContent: 'center',
    shadowColor: '#000000',
    shadowOffset: { height: 3, width: 0 },
    shadowOpacity: 0.18,
    shadowRadius: 5,
    width: 64
  },
  logoWrap: {
    alignItems: 'center',
    height: 64,
    justifyContent: 'center',
    width: 64
  },
  logoBolt: {
    color: colors.white,
    fontSize: fontSizes.logo,
    fontWeight: '900',
    lineHeight: 34
  },
  logoImage: {
    height: 64,
    width: 64
  },
  appTitle: {
    color: '#1f2529',
    fontSize: fontSizes.brand,
    fontWeight: '800',
    lineHeight: 32,
    marginTop: 18
  },
  appSubtitle: {
    color: '#4b555a',
    fontSize: fontSizes.tiny,
    lineHeight: 16,
    marginBottom: 4,
    textAlign: 'center'
  },
  fieldGroup: {
    gap: 6,
    marginTop: 16,
    width: '100%'
  },
  inputLabel: {
    color: '#25292d',
    fontSize: fontSizes.label,
    fontWeight: '800',
    lineHeight: 16
  },
  input: {
    backgroundColor: '#e9eaec',
    borderRadius: 8,
    color: '#1f2529',
    fontSize: fontSizes.bodyLarge,
    minHeight: 48,
    paddingHorizontal: 16
  },
  passwordLabelRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between'
  },
  forgotText: {
    color: colors.primary,
    fontSize: fontSizes.caption,
    fontWeight: '800'
  },
  loginButton: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 7,
    justifyContent: 'center',
    marginTop: 34,
    minHeight: 49,
    width: '100%'
  },
  disabledButton: {
    opacity: 0.5
  },
  loginButtonText: {
    color: colors.white,
    fontSize: fontSizes.bodyLarge,
    fontWeight: '500'
  },
  errorText: {
    alignSelf: 'flex-start',
    color: '#b32126',
    fontSize: fontSizes.caption,
    fontWeight: '700',
    lineHeight: 18,
    marginTop: 12
  },
  signupSeparator: {
    backgroundColor: '#cfd8de',
    height: 1,
    marginTop: 32,
    width: '100%'
  },
  dividerRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    marginTop: 38,
    width: '100%'
  },
  divider: {
    backgroundColor: '#cfd8de',
    flex: 1,
    height: 1
  },
  dividerText: {
    color: '#435158',
    fontSize: fontSizes.label,
    fontWeight: '800',
    lineHeight: 18
  },
  googleButton: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderColor: '#b8c8cf',
    borderRadius: 7,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'center',
    marginTop: 50,
    minHeight: 48,
    width: 156
  },
  googleLogo: {
    color: '#4285f4',
    fontSize: fontSizes.label,
    fontWeight: '900'
  },
  googleText: {
    color: '#2d3135',
    fontSize: fontSizes.label,
    fontWeight: '800'
  }
});

export const profileSelectionStyles = StyleSheet.create({
  page: {
    alignItems: 'center',
    backgroundColor: colors.background,
    flex: 1,
    minHeight: '100%',
    width: '100%'
  },
  contentShell: {
    flex: 1,
    maxWidth: layout.authPageMaxWidth,
    minHeight: '100%',
    width: '100%'
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 64,
    paddingHorizontal: 22
  },
  backButton: {
    alignItems: 'center',
    height: 40,
    justifyContent: 'center',
    width: 40
  },
  backIcon: {
    color: colors.text,
    fontSize: fontSizes.iconLarge,
    fontWeight: '300',
    lineHeight: 34
  },
  brand: {
    color: colors.text,
    fontSize: fontSizes.brand,
    fontWeight: '800',
    lineHeight: 32
  },
  headerSpacer: {
    width: 40
  },
  content: {
    gap: 16,
    paddingHorizontal: 28,
    paddingTop: 28,
    paddingBottom: 120
  },
  title: {
    color: '#1f2529',
    fontSize: fontSizes.display,
    fontWeight: '800',
    lineHeight: 34
  },
  subtitle: {
    color: '#4a555a',
    fontSize: fontSizes.bodyLarge,
    lineHeight: 24,
    marginBottom: 16,
    maxWidth: 360
  },
  roleCard: {
    alignItems: 'flex-start',
    backgroundColor: '#fbfcfd',
    borderColor: '#d7dce0',
    borderRadius: 6,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 16,
    minHeight: 158,
    paddingHorizontal: 16,
    paddingVertical: 18,
    shadowColor: '#000000',
    shadowOffset: { height: 2, width: 0 },
    shadowOpacity: 0.1,
    shadowRadius: 5
  },
  selectedRoleCard: {
    backgroundColor: '#effdfe',
    borderColor: colors.primary,
    borderWidth: 2,
    shadowOpacity: 0
  },
  roleIcon: {
    alignItems: 'center',
    backgroundColor: '#e2e4e6',
    borderRadius: 24,
    height: 48,
    justifyContent: 'center',
    width: 48
  },
  selectedRoleIcon: {
    backgroundColor: colors.primary
  },
  roleText: {
    flex: 1,
    gap: 6
  },
  roleTitle: {
    color: '#1f2529',
    fontSize: fontSizes.icon,
    fontWeight: '800',
    lineHeight: 25
  },
  roleDescription: {
    color: '#4a555a',
    fontSize: fontSizes.body,
    lineHeight: 24
  },
  radio: {
    alignItems: 'center',
    borderColor: '#b9c9cf',
    borderRadius: 12,
    borderWidth: 2,
    height: 24,
    justifyContent: 'center',
    marginTop: 1,
    width: 24
  },
  selectedRadio: {
    backgroundColor: colors.text,
    borderColor: colors.text
  },
  radioCheck: {
    color: colors.white,
    fontSize: fontSizes.control,
    fontWeight: '800',
    lineHeight: 18
  },
  footer: {
    backgroundColor: colors.white,
    borderTopColor: '#edf0f2',
    borderTopWidth: 1,
    bottom: 0,
    left: 0,
    padding: 20,
    position: 'absolute',
    right: 0,
    shadowColor: '#000000',
    shadowOffset: { height: -2, width: 0 },
    shadowOpacity: 0.08,
    shadowRadius: 10
  },
  continueButton: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 7,
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'center',
    minHeight: 57
  },
  continueText: {
    color: colors.white,
    fontSize: fontSizes.bodyLarge,
    fontWeight: '500'
  }
});

export const registrationScreenStyles = StyleSheet.create({
  page: {
    backgroundColor: colors.background,
    flex: 1,
    height: '100%',
    overflow: 'hidden'
  },
  header: {
    borderBottomColor: '#dce4e8',
    borderBottomWidth: 1,
    minHeight: 64,
    justifyContent: 'center',
    paddingHorizontal: 20
  },
  backButton: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
    minHeight: 42
  },
  backText: {
    color: colors.text,
    fontSize: fontSizes.bodyLarge,
    fontWeight: '600'
  },
  content: {
    gap: 18,
    marginHorizontal: 'auto',
    maxWidth: layout.authPageMaxWidth,
    paddingHorizontal: 20,
    paddingTop: 32,
    width: '100%'
  },
  title: {
    color: '#1f2529',
    fontSize: fontSizes.title,
    fontWeight: '900',
    lineHeight: 30
  },
  subtitle: {
    color: '#4b555a',
    fontSize: fontSizes.control,
    lineHeight: 20,
    marginTop: -12
  },
  fieldGroup: {
    gap: 8,
    width: '100%'
  },
  label: {
    color: '#1f2529',
    fontSize: fontSizes.caption,
    fontWeight: '900',
    lineHeight: 16
  },
  input: {
    backgroundColor: colors.white,
    borderColor: '#d8e1e7',
    borderRadius: 8,
    borderWidth: 1,
    color: '#1f2529',
    fontSize: fontSizes.bodyLarge,
    minHeight: 48,
    paddingHorizontal: 16
  },
  select: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderColor: '#d8e1e7',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    minHeight: 48,
    paddingHorizontal: 16
  },
  selectToggle: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    minHeight: 48
  },
  selectText: {
    color: '#1f2529',
    flex: 1,
    fontSize: fontSizes.bodyLarge
  },
  placeholderText: {
    color: '#9aa4a9'
  },
  chevron: {
    color: '#4b555a',
    fontSize: fontSizes.icon,
    fontWeight: '900'
  },
  selectMenu: {
    backgroundColor: colors.white,
    borderColor: '#d8e1e7',
    borderRadius: 8,
    borderWidth: 1,
    maxHeight: 220
  },
  selectOption: {
    borderBottomColor: '#edf2f4',
    borderBottomWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 10
  },
  selectedSelectOption: {
    backgroundColor: '#e9fbfc'
  },
  selectBackdrop: {
    backgroundColor: 'rgba(15, 36, 45, 0.32)',
    flex: 1,
    justifyContent: 'flex-end',
    padding: 20
  },
  selectModal: {
    backgroundColor: colors.white,
    borderRadius: 8,
    maxHeight: '70%',
    overflow: 'hidden',
    paddingVertical: 8
  },
  selectModalTitle: {
    color: colors.text,
    fontSize: fontSizes.bodyLarge,
    fontWeight: '900',
    paddingHorizontal: 16,
    paddingVertical: 12
  },
  selectOptionText: {
    color: '#1f2529',
    fontSize: fontSizes.control,
    fontWeight: '800',
    lineHeight: 18
  },
  selectOptionMeta: {
    color: '#6b767b',
    fontSize: fontSizes.caption,
    lineHeight: 16,
    marginTop: 2
  },
  connectorRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10
  },
  connectorPill: {
    alignItems: 'center',
    backgroundColor: '#f5f8f9',
    borderColor: '#d8e1e7',
    borderRadius: 999,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 44,
    paddingHorizontal: 17
  },
  selectedConnectorPill: {
    backgroundColor: '#e9fbfc',
    borderColor: colors.primary,
    borderWidth: 2
  },
  connectorText: {
    color: '#1f2529',
    fontSize: fontSizes.bodyLarge,
    lineHeight: 20
  },
  selectedConnectorText: {
    color: colors.text,
    fontWeight: '800'
  },
  thresholdHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between'
  },
  thresholdValue: {
    color: colors.text,
    fontSize: fontSizes.control,
    fontWeight: '900'
  },
  helperText: {
    color: '#4b555a',
    fontSize: fontSizes.tiny,
    lineHeight: 16,
    marginTop: -5
  },
  thresholdTrack: {
    backgroundColor: '#dde5e8',
    borderRadius: 999,
    height: 7,
    justifyContent: 'center',
    marginTop: 16
  },
  thresholdFill: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: 7
  },
  thresholdThumb: {
    backgroundColor: colors.primary,
    borderColor: colors.white,
    borderRadius: 10,
    borderWidth: 2,
    height: 20,
    position: 'absolute',
    transform: [{ translateX: -10 }],
    width: 20
  },
  thresholdHitRow: {
    bottom: -14,
    flexDirection: 'row',
    left: 0,
    position: 'absolute',
    right: 0,
    top: -14
  },
  thresholdHitTarget: {
    flex: 1
  },
  thresholdLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between'
  },
  thresholdLabel: {
    color: '#4b555a',
    fontSize: fontSizes.tiny,
    lineHeight: 16
  },
  permissionCard: {
    alignItems: 'flex-start',
    backgroundColor: '#dffbfc',
    borderRadius: 8,
    flexDirection: 'row',
    gap: 12,
    padding: 16
  },
  checkbox: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderColor: '#b7dfe2',
    borderRadius: 6,
    borderWidth: 1,
    height: 20,
    justifyContent: 'center',
    marginTop: 1,
    width: 20
  },
  checkedBox: {
    backgroundColor: colors.primary,
    borderColor: colors.primary
  },
  checkText: {
    color: colors.white,
    fontSize: fontSizes.caption,
    fontWeight: '900',
    lineHeight: 16
  },
  permissionTextWrap: {
    flex: 1,
    gap: 10
  },
  permissionTitle: {
    color: colors.text,
    fontSize: fontSizes.caption,
    fontWeight: '900',
    lineHeight: 18
  },
  permissionBody: {
    color: '#4b555a',
    fontSize: fontSizes.caption,
    lineHeight: 18
  },
  registerButton: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 8,
    justifyContent: 'center',
    marginTop: 6,
    minHeight: 56
  },
  disabledButton: {
    opacity: 0.5
  },
  registerButtonText: {
    color: colors.white,
    fontSize: fontSizes.bodyLarge,
    fontWeight: '900'
  },
  errorText: {
    color: '#b32126',
    fontSize: fontSizes.caption,
    fontWeight: '700',
    lineHeight: 18,
    marginTop: -4
  },
  loginPrompt: {
    color: '#4b555a',
    fontSize: fontSizes.control,
    lineHeight: 20,
    marginTop: 14,
    textAlign: 'center'
  },
  loginLink: {
    color: colors.text,
    fontWeight: '800'
  },
  homeIndicator: {
    alignSelf: 'center',
    backgroundColor: '#c9d0d3',
    borderRadius: 999,
    height: 4,
    marginTop: 8,
    width: 130
  },
  poweredBy: {
    color: '#b6bfc4',
    fontSize: fontSizes.eyebrow,
    fontWeight: '900',
    letterSpacing: 1.5,
    lineHeight: 16,
    marginTop: 22,
    textAlign: 'center'
  }
});

export const mockDriverScreenStyles = StyleSheet.create({
  page: {
    alignItems: 'center',
    backgroundColor: colors.background,
    flex: 1,
    justifyContent: 'center',
    padding: 24
  },
  title: {
    color: colors.text,
    fontSize: fontSizes.display,
    fontWeight: '900',
    lineHeight: 34
  },
  body: {
    color: '#4a555a',
    fontSize: fontSizes.body,
    lineHeight: 22,
    marginTop: 8,
    maxWidth: 320,
    textAlign: 'center'
  }
});

export const evDriverContainerStyles = StyleSheet.create({
  shell: {
    backgroundColor: colors.background,
    flex: 1,
    flexDirection: 'row',
    minHeight: '100%'
  },
  viewportShell: {
    overflow: 'hidden'
  },
  content: {
    flex: 1,
    position: 'relative'
  },
  viewportContent: {
    height: '100%',
    maxHeight: '100%',
    overflow: 'hidden'
  },
  sidebarWrap: {
    backgroundColor: colors.background,
    flexBasis: layout.sidebarWidth,
    flexGrow: 0,
    flexShrink: 0,
    width: layout.sidebarWidth
  },
  bottomNavWrap: {
    backgroundColor: colors.background,
    bottom: 0,
    left: 0,
    position: 'absolute',
    right: 0
  },
  sidebarNote: {
    color: colors.text,
    fontSize: fontSizes.label,
    fontWeight: '800',
    lineHeight: 18
  }
});

export const filterCategoryStyles = StyleSheet.create({
  category: {
    gap: 9
  },
  title: {
    color: '#4c5960',
    fontSize: fontSizes.eyebrow,
    fontWeight: '900',
    letterSpacing: 1,
    lineHeight: 13,
    textTransform: 'uppercase'
  },
  pillOptions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8
  },
  pillOption: {
    alignItems: 'center',
    backgroundColor: '#e9ecef',
    borderColor: '#cad2d7',
    borderRadius: 999,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 28,
    paddingHorizontal: 15
  },
  selectedOption: {
    backgroundColor: colors.primary,
    borderColor: colors.primary
  },
  pillLabel: {
    color: '#1f2529',
    fontSize: fontSizes.caption,
    fontWeight: '600',
    lineHeight: 16
  },
  selectedLabel: {
    color: colors.text
  },
  cardOptions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12
  },
  cardOption: {
    backgroundColor: '#e9ecef',
    borderColor: '#cad2d7',
    borderRadius: 10,
    borderWidth: 1,
    minHeight: 58,
    paddingHorizontal: 13,
    paddingVertical: 12,
    position: 'relative',
    width: '30.8%'
  },
  cardTickIcon: {
    position: 'absolute',
    right: 10,
    top: 10
  },
  cardLabel: {
    color: '#1f2529',
    fontSize: fontSizes.control,
    fontWeight: '800',
    lineHeight: 18
  },
  description: {
    color: '#718087',
    fontSize: fontSizes.eyebrow,
    lineHeight: 14,
    marginTop: 4
  },
  selectedDescription: {
    color: colors.text
  }
});

export const walletScreenStyles = StyleSheet.create({
  page: {
    backgroundColor: '#f7f8fd',
    flex: 1
  },
  content: {
    gap: 16,
    marginHorizontal: 'auto',
    maxWidth: 520,
    paddingHorizontal: 24,
    width: '100%'
  },
  balanceCard: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderColor: '#eef1f5',
    borderRadius: 10,
    borderWidth: 1,
    boxShadow: '0 6px 20px rgba(15, 36, 45, 0.05)',
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 94,
    paddingHorizontal: 20
  },
  balanceLabel: {
    color: '#4d5961',
    fontSize: fontSizes.caption,
    fontWeight: '800',
    letterSpacing: 0.4,
    lineHeight: 16
  },
  balanceValue: {
    color: '#151c2a',
    fontSize: fontSizes.titleSmall,
    fontWeight: '900',
    lineHeight: 30,
    marginTop: 8
  },
  topUpButton: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 8,
    justifyContent: 'center',
    minHeight: 44,
    paddingHorizontal: 18
  },
  topUpButtonText: {
    color: colors.text,
    fontSize: fontSizes.caption,
    fontWeight: '800'
  },
  historyHeader: {
    alignItems: 'center',
    backgroundColor: '#f7f8fd',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginHorizontal: -2,
    paddingBottom: 4,
    paddingTop: 12,
    zIndex: 2
  },
  pinnedHistoryShell: {
    alignItems: 'center',
    backgroundColor: '#f7f8fd',
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
    zIndex: 20
  },
  pinnedHistoryInner: {
    backgroundColor: '#f7f8fd',
    maxWidth: 520,
    paddingHorizontal: 24,
    width: '100%'
  },
  historyTitle: {
    color: '#151c2a',
    fontSize: fontSizes.titleMedium,
    fontWeight: '900',
    lineHeight: 28
  },
  filterButton: {
    alignItems: 'center',
    height: 34,
    justifyContent: 'center',
    width: 34
  },
  transactionList: {
    gap: 14
  },
  transactionCard: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderRadius: 10,
    flexDirection: 'row',
    gap: 14,
    minHeight: 102,
    paddingHorizontal: 12,
    paddingVertical: 14
  },
  transactionIcon: {
    alignItems: 'center',
    backgroundColor: '#d4edf0',
    borderRadius: 24,
    height: 48,
    justifyContent: 'center',
    width: 48
  },
  failedTransactionIcon: {
    backgroundColor: '#ffd9d6'
  },
  transactionIconText: {
    color: '#5f7075',
    fontSize: fontSizes.titleMedium,
    fontWeight: '900'
  },
  failedTransactionIconText: {
    color: '#b32126'
  },
  transactionBody: {
    flex: 1,
    gap: 5
  },
  transactionTitle: {
    color: '#151c2a',
    fontSize: fontSizes.control,
    fontWeight: '900',
    lineHeight: 20
  },
  transactionMeta: {
    color: '#4f5b64',
    fontSize: fontSizes.tiny,
    lineHeight: 16
  },
  transactionAmountWrap: {
    alignItems: 'flex-end',
    gap: 8,
    minWidth: 84
  },
  transactionAmount: {
    color: '#151c2a',
    fontSize: fontSizes.control,
    fontWeight: '900'
  },
  positiveAmount: {
    color: '#00696f'
  },
  statusBadge: {
    backgroundColor: '#cfe9ec',
    borderRadius: 4,
    paddingHorizontal: 8,
    paddingVertical: 4
  },
  failedStatusBadge: {
    backgroundColor: '#ffd9d6'
  },
  statusBadgeText: {
    color: '#4f696d',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.7
  },
  failedStatusBadgeText: {
    color: '#b32126'
  },
  cashbackBanner: {
    backgroundColor: colors.text,
    borderRadius: 14,
    marginTop: 16,
    minHeight: 128,
    overflow: 'hidden',
    paddingHorizontal: 24,
    paddingVertical: 24
  },
  cashbackTitle: {
    color: colors.white,
    fontSize: fontSizes.titleMedium,
    fontWeight: '900',
    lineHeight: 28
  },
  cashbackText: {
    color: '#b7eef1',
    fontSize: fontSizes.caption,
    lineHeight: 18,
    marginTop: 6
  },
  cashbackCta: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderRadius: 999,
    justifyContent: 'center',
    marginTop: 12,
    minHeight: 24,
    width: 88
  },
  cashbackCtaText: {
    color: colors.text,
    fontSize: fontSizes.tiny,
    fontWeight: '800'
  },
  modalOverlay: {
    flex: 1
  },
  centeredModalOverlay: {
    alignItems: 'center',
    backgroundColor: 'rgba(15, 23, 32, 0.36)',
    justifyContent: 'center',
    padding: 24
  },
  bottomModalOverlay: {
    backgroundColor: 'rgba(15, 23, 32, 0.24)',
    justifyContent: 'flex-end'
  },
  detailSheet: {
    backgroundColor: colors.white,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden'
  },
  desktopDetailSheet: {
    borderRadius: 14,
    maxWidth: 430,
    width: '100%'
  },
  mobileDetailSheet: {
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    height: '100%',
    width: '100%'
  },
  detailHeader: {
    alignItems: 'center',
    borderBottomColor: '#eef1f4',
    borderBottomWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 64,
    paddingHorizontal: 18
  },
  closeButton: {
    alignItems: 'center',
    height: 40,
    justifyContent: 'center',
    width: 40
  },
  detailHeaderTitle: {
    color: colors.text,
    fontSize: fontSizes.titleMedium,
    fontWeight: '900'
  },
  detailContent: {
    paddingBottom: 24,
    paddingHorizontal: 24,
    paddingTop: 32
  },
  detailResultIcon: {
    alignItems: 'center',
    alignSelf: 'center',
    backgroundColor: '#c9f7fb',
    borderRadius: 32,
    height: 64,
    justifyContent: 'center',
    width: 64
  },
  failedDetailResultIcon: {
    backgroundColor: '#ffd9d6'
  },
  detailResultIconText: {
    color: colors.primary,
    fontSize: fontSizes.titleMedium,
    fontWeight: '900'
  },
  failedDetailResultIconText: {
    color: '#b32126'
  },
  detailAmount: {
    color: '#151c2a',
    fontSize: 30,
    fontWeight: '900',
    lineHeight: 38,
    marginTop: 18,
    textAlign: 'center'
  },
  detailType: {
    color: '#6b7280',
    fontSize: fontSizes.body,
    fontWeight: '600',
    marginTop: 4,
    textAlign: 'center'
  },
  detailSummaryCard: {
    alignItems: 'center',
    borderColor: '#edf1f4',
    borderRadius: 10,
    borderWidth: 1,
    boxShadow: '0 2px 6px rgba(15, 36, 45, 0.04)',
    flexDirection: 'row',
    gap: 14,
    marginTop: 40,
    minHeight: 74,
    paddingHorizontal: 16
  },
  detailSummaryIcon: {
    alignItems: 'center',
    backgroundColor: '#f0f2f5',
    borderRadius: 7,
    height: 40,
    justifyContent: 'center',
    width: 40
  },
  detailSummaryIconText: {
    color: '#4b5563',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '900'
  },
  detailSummaryTitle: {
    color: '#151c2a',
    fontSize: fontSizes.control,
    fontWeight: '900'
  },
  detailSummaryMeta: {
    color: '#6b7280',
    fontSize: fontSizes.caption,
    marginTop: 3
  },
  detailSectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 32,
    minHeight: 36
  },
  detailSectionTitle: {
    color: '#6b7280',
    fontSize: fontSizes.caption,
    fontWeight: '900',
    letterSpacing: 1
  },
  detailChevron: {
    color: '#9aa4a9',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '800'
  },
  detailRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 36
  },
  detailLabel: {
    color: '#6b7280',
    flex: 1,
    fontSize: fontSizes.control
  },
  detailValue: {
    color: '#53606a',
    flex: 1.25,
    fontSize: fontSizes.control,
    fontWeight: '600',
    textAlign: 'right'
  },
  detailStrongValue: {
    color: '#151c2a',
    fontWeight: '900'
  },
  successText: {
    color: '#00b875',
    fontWeight: '900'
  },
  failedText: {
    color: '#b32126',
    fontWeight: '900'
  },
  detailDivider: {
    backgroundColor: '#e5eaee',
    height: 1,
    marginVertical: 8
  },
  detailTotalLabel: {
    color: '#151c2a',
    fontWeight: '900'
  },
  detailTotalValue: {
    color: '#151c2a',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '900'
  },
  invoiceFooter: {
    backgroundColor: colors.white,
    borderTopColor: '#eef1f4',
    borderTopWidth: 1,
    paddingBottom: 24,
    paddingHorizontal: 24,
    paddingTop: 16
  },
  invoiceButton: {
    alignItems: 'center',
    borderColor: colors.primary,
    borderRadius: 999,
    borderWidth: 2,
    justifyContent: 'center',
    minHeight: 56
  },
  invoiceButtonText: {
    color: colors.text,
    fontSize: fontSizes.control,
    fontWeight: '900'
  },
  topupHeader: {
    alignItems: 'center',
    backgroundColor: '#f7f8fd',
    flexDirection: 'row',
    gap: 12,
    minHeight: 76,
    paddingHorizontal: 24
  },
  topupBackButton: {
    alignItems: 'center',
    height: 44,
    justifyContent: 'center',
    width: 44
  },
  topupBackIcon: {
    color: colors.text,
    fontSize: fontSizes.iconLarge,
    fontWeight: '400',
    lineHeight: 36
  },
  topupHeaderTitle: {
    color: colors.text,
    flex: 1,
    fontSize: fontSizes.titleSmall,
    fontWeight: '900',
    lineHeight: 28
  },
  topupSuccessHeaderTitle: {
    color: '#00a7ae'
  },
  topupHeaderSpacer: {
    width: 44
  },
  topupContent: {
    gap: 28,
    marginHorizontal: 'auto',
    maxWidth: 520,
    paddingHorizontal: 24,
    paddingTop: 20,
    width: '100%'
  },
  topupBalanceCard: {
    alignItems: 'center',
    backgroundColor: '#eefafa',
    borderRadius: 20,
    boxShadow: '0 4px 10px rgba(15, 36, 45, 0.05)',
    flexDirection: 'row',
    gap: 18,
    justifyContent: 'space-between',
    minHeight: 142,
    overflow: 'hidden',
    paddingHorizontal: 24
  },
  topupBalanceLabel: {
    color: '#617089',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '600',
    lineHeight: 24
  },
  topupBalanceValue: {
    color: '#10172b',
    fontSize: fontSizes.title,
    fontWeight: '900',
    lineHeight: 36,
    marginTop: 16
  },
  topupWalletBadge: {
    alignItems: 'center',
    backgroundColor: '#0bb8ae',
    borderRadius: 16,
    flexShrink: 0,
    height: 76,
    justifyContent: 'center',
    position: 'relative',
    width: 76
  },
  topupCurrencyBubble: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderRadius: 18,
    bottom: 12,
    height: 32,
    justifyContent: 'center',
    position: 'absolute',
    right: 8,
    width: 32
  },
  topupCurrencyText: {
    color: '#0bb8ae',
    fontSize: fontSizes.control,
    fontWeight: '900'
  },
  topupFormSection: {
    gap: 14,
    marginTop: 12
  },
  topupSectionTitle: {
    color: '#10172b',
    fontSize: fontSizes.heading,
    fontWeight: '900',
    lineHeight: 24
  },
  topupInputWrap: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderColor: '#596274',
    borderRadius: 20,
    borderWidth: 1.5,
    flexDirection: 'row',
    gap: 18,
    minHeight: 82,
    paddingHorizontal: 28
  },
  topupPrefix: {
    color: '#0bb8ae',
    fontSize: fontSizes.heading,
    fontWeight: '900'
  },
  topupInput: {
    color: '#10172b',
    flex: 1,
    fontSize: fontSizes.heading,
    fontWeight: '600',
    minHeight: 54
  },
  topupHelperRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    minHeight: 28
  },
  topupInfoIcon: {
    alignItems: 'center',
    borderColor: '#0bb8ae',
    borderRadius: 14,
    borderWidth: 1.5,
    height: 28,
    justifyContent: 'center',
    width: 28
  },
  topupInfoIconText: {
    color: '#0bb8ae',
    fontSize: fontSizes.control,
    fontWeight: '900'
  },
  topupHelperText: {
    color: '#8b99ad',
    fontSize: fontSizes.control,
    lineHeight: 20
  },
  topupErrorText: {
    color: '#b32126'
  },
  topupPrimaryButton: {
    alignItems: 'center',
    backgroundColor: '#0bb8ae',
    borderRadius: 20,
    flexDirection: 'row',
    gap: 16,
    justifyContent: 'center',
    minHeight: 86
  },
  topupDisabledButton: {
    opacity: 0.5
  },
  topupPrimaryButtonText: {
    color: colors.white,
    fontSize: fontSizes.heading,
    fontWeight: '900'
  },
  topupTrustCard: {
    alignItems: 'center',
    backgroundColor: '#eefafa',
    borderRadius: 20,
    flexDirection: 'row',
    gap: 24,
    minHeight: 150,
    paddingHorizontal: 28
  },
  topupTrustIcon: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderColor: '#e3eaf0',
    borderRadius: 32,
    borderWidth: 1,
    boxShadow: '0 3px 8px rgba(15, 36, 45, 0.12)',
    height: 64,
    justifyContent: 'center',
    width: 64
  },
  topupTrustTextWrap: {
    flex: 1,
    gap: 12
  },
  topupTrustTitle: {
    color: '#10172b',
    fontSize: fontSizes.heading,
    fontWeight: '900'
  },
  topupTrustText: {
    color: '#617089',
    fontSize: fontSizes.control,
    lineHeight: 22
  },
  topupSuccessContent: {
    alignItems: 'center',
    flex: 1,
    marginHorizontal: 'auto',
    maxWidth: 520,
    paddingHorizontal: 24,
    paddingTop: 72,
    width: '100%'
  },
  topupSuccessMarkWrap: {
    alignItems: 'center',
    height: 210,
    justifyContent: 'center',
    position: 'relative',
    width: 260
  },
  topupSuccessMark: {
    alignItems: 'center',
    backgroundColor: '#0aaeb6',
    borderRadius: 100,
    boxShadow: '0 16px 28px rgba(11, 184, 174, 0.18)',
    height: 170,
    justifyContent: 'center',
    width: 170
  },
  topupSuccessCheck: {
    color: colors.white,
    fontSize: 92,
    fontWeight: '400',
    lineHeight: 104
  },
  topupConfettiDotLarge: {
    backgroundColor: '#a6e2e7',
    borderRadius: 5,
    height: 10,
    left: 36,
    position: 'absolute',
    top: 48,
    width: 10
  },
  topupConfettiDotSmall: {
    backgroundColor: '#a6e2e7',
    borderRadius: 4,
    height: 8,
    position: 'absolute',
    right: 28,
    top: 164,
    width: 8
  },
  topupConfettiDotTiny: {
    backgroundColor: '#a6e2e7',
    borderRadius: 3,
    height: 6,
    position: 'absolute',
    right: 72,
    top: 10,
    width: 6
  },
  topupSuccessTitle: {
    color: '#10172b',
    fontSize: fontSizes.title,
    fontWeight: '900',
    lineHeight: 30,
    marginTop: 26,
    textAlign: 'center'
  },
  topupSuccessAmount: {
    color: '#10172b',
    fontSize: fontSizes.display,
    fontWeight: '900',
    lineHeight: 36,
    marginTop: 22,
    textAlign: 'center'
  },
  topupSuccessSubtitle: {
    color: '#8b99ad',
    fontSize: fontSizes.control,
    lineHeight: 22,
    marginTop: 18,
    maxWidth: 300,
    textAlign: 'center'
  },
  topupSuccessSpacer: {
    flex: 1
  },
  topupDoneButton: {
    alignItems: 'center',
    alignSelf: 'stretch',
    backgroundColor: '#0aaeb6',
    borderRadius: 20,
    boxShadow: '0 12px 22px rgba(11, 184, 174, 0.18)',
    justifyContent: 'center',
    minHeight: 82
  },
  topupDoneButtonText: {
    color: colors.white,
    fontSize: fontSizes.heading,
    fontWeight: '900'
  }
});

export const driverMapStyles = StyleSheet.create({
  page: {
    backgroundColor: colors.background,
    flex: 1,
    overflow: 'hidden'
  },
  searchBar: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderRadius: 12,
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.12)',
    flexDirection: 'row',
    gap: 12,
    left: 22,
    minHeight: 66,
    paddingHorizontal: 16,
    position: 'absolute',
    right: 22,
    zIndex: 9999
  },
  searchIcon: {
    alignItems: 'center',
    height: 18,
    justifyContent: 'center',
    width: 18
  },
  searchInput: {
    color: '#1f2529',
    flex: 1,
    fontSize: fontSizes.body,
    minHeight: 40
  },
  filterIcon: {
    alignItems: 'center',
    height: 36,
    justifyContent: 'center',
    width: 36
  },
  filterIconText: {
    color: colors.text,
    fontSize: fontSizes.titleMedium,
    fontWeight: '900'
  },
  sheet: {
    backgroundColor: colors.white,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    boxShadow: '0 -4px 14px rgba(0, 0, 0, 0.12)',
    left: 0,
    overflow: 'hidden',
    paddingBottom: 20,
    paddingHorizontal: 22,
    position: 'absolute',
    right: 0,
    zIndex: 9999
  },
  drawerHandleWrap: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 24
  },
  drawerHandle: {
    backgroundColor: '#b7c9cc',
    borderRadius: 999,
    height: 4,
    width: 48
  },
  drawerBody: {
    flex: 1
  },
  sheetHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 18
  },
  sheetTitle: {
    color: '#1f2529',
    fontSize: fontSizes.titleSmall,
    fontWeight: '900',
    lineHeight: 27
  },
  closeButton: {
    alignItems: 'center',
    height: 36,
    justifyContent: 'center',
    width: 36
  },
  closeText: {
    color: '#11181c',
    fontSize: fontSizes.icon,
    fontWeight: '700',
    lineHeight: 24
  },
  expandedContent: {
    flex: 1,
    gap: 12
  },
  filterContent: {
    gap: 24,
    paddingBottom: 14
  },
  categoryTitle: {
    color: '#4c5960',
    fontSize: fontSizes.eyebrow,
    fontWeight: '900',
    letterSpacing: 1,
    lineHeight: 13,
    textTransform: 'uppercase'
  },
  distanceSection: {
    gap: 11
  },
  distanceHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between'
  },
  distanceValue: {
    color: colors.text,
    fontSize: fontSizes.caption,
    fontWeight: '900'
  },
  sliderTrack: {
    backgroundColor: '#c8d5d8',
    borderRadius: 999,
    height: 4,
    justifyContent: 'center',
    marginHorizontal: 8
  },
  sliderFill: {
    backgroundColor: colors.text,
    borderRadius: 999,
    height: 4,
    width: '66%'
  },
  sliderThumb: {
    backgroundColor: colors.text,
    borderColor: colors.white,
    borderRadius: 9,
    borderWidth: 2,
    height: 18,
    left: '64%',
    position: 'absolute',
    transform: [{ translateX: -9 }],
    width: 18
  },
  sliderHitRow: {
    bottom: -16,
    flexDirection: 'row',
    left: 0,
    position: 'absolute',
    right: 0,
    top: -16
  },
  sliderHitTarget: {
    flex: 1
  },
  sliderLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 8
  },
  sliderLabel: {
    color: '#4c5960',
    fontSize: fontSizes.eyebrow,
    lineHeight: 14
  },
  sliderLabelSelected: {
    color: colors.text,
    fontWeight: '900'
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
    paddingTop: 4
  },
  resetButton: {
    alignItems: 'center',
    backgroundColor: '#c8f7fa',
    borderColor: colors.primary,
    borderRadius: 9,
    borderWidth: 1,
    flex: 1,
    justifyContent: 'center',
    minHeight: 46
  },
  resetButtonText: {
    color: colors.text,
    fontSize: fontSizes.control,
    fontWeight: '800'
  },
  applyButton: {
    alignItems: 'center',
    backgroundColor: colors.text,
    borderRadius: 9,
    flex: 1,
    justifyContent: 'center',
    minHeight: 46
  },
  applyButtonText: {
    color: colors.white,
    fontSize: fontSizes.control,
    fontWeight: '800'
  },
  resultsHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 16
  },
  resultsTitle: {
    color: '#1f2529',
    flex: 1,
    fontSize: fontSizes.titleSmall,
    fontWeight: '900',
    lineHeight: 27
  },
  filterButton: {
    alignItems: 'center',
    backgroundColor: '#eceeef',
    borderColor: '#d8dee1',
    borderRadius: 11,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 7,
    justifyContent: 'center',
    minHeight: 38,
    paddingHorizontal: 13
  },
  filterButtonIcon: {
    color: '#4c5960',
    fontSize: fontSizes.control,
    fontWeight: '900'
  },
  filterButtonText: {
    color: '#2b3337',
    fontSize: fontSizes.label,
    fontWeight: '700'
  },
  locationPermissionCard: {
    backgroundColor: '#eefafb',
    borderColor: '#bce9ed',
    borderRadius: 8,
    borderWidth: 1,
    gap: 12,
    padding: 14
  },
  locationPermissionTextWrap: {
    gap: 4
  },
  locationPermissionTitle: {
    color: colors.text,
    fontSize: fontSizes.control,
    fontWeight: '900',
    lineHeight: 18
  },
  locationPermissionBody: {
    color: '#4e5d63',
    fontSize: fontSizes.caption,
    lineHeight: 18
  },
  locationPermissionButton: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: colors.text,
    borderRadius: 8,
    justifyContent: 'center',
    minHeight: 40,
    paddingHorizontal: 14
  },
  locationPermissionButtonDisabled: {
    backgroundColor: '#7b8b90'
  },
  locationPermissionButtonText: {
    color: colors.white,
    fontSize: fontSizes.label,
    fontWeight: '800'
  },
  stationList: {
    gap: 12,
    paddingBottom: 24
  },
  stationCard: {
    backgroundColor: colors.white,
    borderColor: '#dce4e7',
    borderRadius: 14,
    borderWidth: 1,
    gap: 8,
    padding: 20
  },
  stationName: {
    color: '#25292d',
    fontSize: fontSizes.icon,
    fontWeight: '500',
    lineHeight: 26
  },
  stationAddress: {
    color: '#6b767b',
    fontSize: fontSizes.bodyLarge,
    lineHeight: 22
  },
  connectorList: {
    gap: 6,
    marginTop: 4
  },
  stationDetailContent: {
    gap: 12,
    paddingBottom: 24
  },
  connectorRow: {
    alignItems: 'center',
    backgroundColor: '#f8f8f9',
    borderColor: '#eceff1',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 33,
    paddingLeft: 10,
    paddingRight: 14
  },
  connectorLeft: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 9,
    paddingRight: 10
  },
  connectorIcon: {
    alignItems: 'center',
    backgroundColor: '#e9fbfc',
    borderRadius: 14,
    height: 27,
    justifyContent: 'center',
    width: 27
  },
  connectorIconText: {
    color: colors.text,
    fontSize: fontSizes.body,
    fontWeight: '900'
  },
  connectorName: {
    color: '#2b3337',
    fontSize: fontSizes.caption,
    fontWeight: '900'
  },
  connectorMeta: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10
  },
  connectorSpeed: {
    color: '#4e5d63',
    fontSize: fontSizes.micro,
    lineHeight: 11,
    textTransform: 'uppercase'
  },
  connectorDivider: {
    backgroundColor: '#cdd6da',
    height: 14,
    width: 1
  },
  connectorTotal: {
    color: '#4e5d63',
    fontSize: fontSizes.caption,
    lineHeight: 16
  },
  detailTitle: {
    color: '#1f2529',
    flex: 1,
    fontSize: fontSizes.titleSmall,
    fontWeight: '900',
    lineHeight: 27,
    paddingRight: 8
  }
});
