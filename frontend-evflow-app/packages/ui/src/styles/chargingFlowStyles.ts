import { StyleSheet } from 'react-native';
import { colors } from '../theme/colors';
import { fontSizes, layout } from './styles';

export const chargingFlowStyles = StyleSheet.create({
  page: {
    backgroundColor: colors.background,
    flex: 1,
    height: '100%',
    overflow: 'hidden',
    width: '100%'
  },
  header: {
    alignItems: 'center',
    backgroundColor: colors.background,
    borderBottomColor: '#e3eaed',
    borderBottomWidth: 1,
    elevation: 4,
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 64,
    paddingHorizontal: 20,
    shadowColor: '#0f242d',
    shadowOffset: { height: 2, width: 0 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    flexShrink: 0,
    zIndex: 10
  },
  backButton: {
    alignItems: 'center',
    height: 40,
    justifyContent: 'center',
    width: 40
  },
  backIcon: {
    color: '#03454b',
    fontSize: fontSizes.heading,
    fontWeight: '800'
  },
  headerTitle: {
    color: colors.text,
    flexShrink: 1,
    fontSize: fontSizes.titleSmall,
    fontWeight: '800',
    textAlign: 'center'
  },
  headerRight: {
    alignItems: 'center',
    height: 40,
    justifyContent: 'center',
    width: 40
  },
  headerRightIcon: {
    color: colors.text,
    fontSize: fontSizes.heading,
    fontWeight: '600'
  },
  content: {
    gap: 20,
    marginHorizontal: 'auto',
    maxWidth: layout.authPageMaxWidth,
    paddingHorizontal: 24,
    paddingTop: 16,
    paddingBottom: 40,
    width: '100%'
  },
  scrollContent: {
    flexGrow: 1
  },
  scrollBody: {
    flex: 1,
    width: '100%'
  },
  cameraContainer: {
    flex: 1,
    backgroundColor: '#000',
    flexDirection: 'column'
  },
  camera: {
    flex: 1,
    width: '100%'
  },
  cameraOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden'
  },
  cameraCutout: {
    width: 250,
    height: 250,
    borderWidth: 2,
    borderColor: '#00e5ff',
    borderRadius: 24,
    backgroundColor: 'transparent'
  },
  cameraTextContainer: {
    position: 'absolute',
    top: '50%',
    marginTop: 141,
    left: 0,
    right: 0,
    alignItems: 'center',
    paddingHorizontal: 20
  },
  cameraInstructions: {
    color: colors.white,
    textAlign: 'center',
    fontSize: fontSizes.control,
    lineHeight: 24,
    paddingHorizontal: 20
  },
  manualEntryLink: {
    color: '#00e5ff',
    textAlign: 'center',
    fontSize: fontSizes.control,
    fontWeight: '600',
    marginTop: 16
  },
  cameraNoticeCard: {
    backgroundColor: '#ffffff',
    padding: 20,
    paddingBottom: 32,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12
  },
  cameraNoticeText: {
    flex: 1,
    color: '#1a2226',
    fontSize: fontSizes.caption,
    lineHeight: 18
  },
  permissionPrompt: {
    alignItems: 'center',
    gap: 14,
    maxWidth: 360,
    paddingHorizontal: 24
  },
  permissionPromptText: {
    color: colors.white,
    fontSize: fontSizes.bodyLarge,
    fontWeight: '700',
    lineHeight: 23,
    textAlign: 'center'
  },
  permissionPromptSubtext: {
    color: '#d9e4e7',
    fontSize: fontSizes.caption,
    lineHeight: 18,
    textAlign: 'center'
  },
  secondaryPermissionButton: {
    alignItems: 'center',
    borderColor: colors.white,
    borderRadius: 8,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 46,
    paddingHorizontal: 18
  },
  secondaryPermissionButtonText: {
    color: colors.white,
    fontSize: fontSizes.control,
    fontWeight: '800',
    textAlign: 'center'
  },
  stationInfoCard: {
    backgroundColor: colors.white,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    padding: 16,
    gap: 12
  },
  stationInfoCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start'
  },
  stationInfoCardImage: {
    alignItems: 'center',
    backgroundColor: '#e0f7fa',
    borderRadius: 10,
    height: 44,
    justifyContent: 'center',
    width: 44
  },
  stationName: {
    color: '#0f242d',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '800'
  },
  stationBadge: {
    backgroundColor: '#d8fcfc',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    alignSelf: 'flex-start'
  },
  stationBadgeText: {
    color: '#019495',
    fontSize: fontSizes.tiny,
    fontWeight: '800'
  },
  stationAddressRow: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'flex-start',
    marginTop: 4
  },
  stationAddressText: {
    color: '#465359',
    fontSize: fontSizes.control,
    flex: 1,
    lineHeight: 20
  },
  sectionTitle: {
    color: '#465359',
    fontSize: fontSizes.caption,
    fontWeight: '800',
    letterSpacing: 1,
    marginTop: 8,
    textTransform: 'uppercase'
  },
  inputWrap: {
    flexDirection: 'row',
    gap: 12
  },
  inputBox: {
    flex: 1,
    backgroundColor: colors.white,
    borderColor: '#b2bdc2',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    height: 56
  },
  inputValue: {
    flex: 1,
    color: '#0f242d',
    fontSize: fontSizes.titleMedium,
    fontWeight: '600'
  },
  inputUnit: {
    color: '#6e7a80',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '500'
  },
  calculateButton: {
    backgroundColor: '#d8e1f5',
    borderRadius: 8,
    paddingHorizontal: 20,
    justifyContent: 'center',
    alignItems: 'center',
    height: 56
  },
  calculateButtonText: {
    color: '#55638c',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '600'
  },
  summaryCard: {
    backgroundColor: '#f3f6f7',
    borderRadius: 8,
    padding: 20,
    gap: 16
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  summaryLabel: {
    color: '#465359',
    fontSize: fontSizes.control,
    lineHeight: 20
  },
  summaryValue: {
    color: '#0f242d',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '600'
  },
  divider: {
    height: 1,
    backgroundColor: '#dee4e6',
    marginVertical: 4
  },
  totalLabel: {
    color: '#0f242d',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '800'
  },
  totalValue: {
    color: '#01c9d8',
    fontSize: fontSizes.title,
    fontWeight: '800'
  },
  summaryHelperText: {
    color: '#6e7a80',
    fontSize: fontSizes.tiny,
    marginTop: 4
  },
  metricsRow: {
    flexDirection: 'row',
    gap: 16
  },
  metricCard: {
    flex: 1,
    backgroundColor: colors.white,
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: 1,
    padding: 16,
    gap: 8
  },
  metricLabel: {
    color: '#6e7a80',
    fontSize: fontSizes.caption,
    fontWeight: '600',
    textTransform: 'uppercase'
  },
  metricValueRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8
  },
  metricValue: {
    color: '#0f242d',
    fontSize: fontSizes.heading,
    fontWeight: '600'
  },
  footerSpacer: {
    flex: 1
  },
  footerAction: {
    gap: 16
  },
  primaryButton: {
    backgroundColor: '#01e0f0',
    borderRadius: 8,
    height: 56,
    justifyContent: 'center',
    alignItems: 'center'
  },
  disabledPrimaryButton: {
    opacity: 0.45
  },
  primaryButtonText: {
    color: '#004a4f',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '700'
  },
  paymentMethodRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8
  },
  buttonIconRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center'
  },
  paymentMethodText: {
    color: '#465359',
    fontSize: fontSizes.control
  },
  successIconWrap: {
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 20,
    marginBottom: 10
  },
  successIconCircle: {
    backgroundColor: '#01e0f0',
    borderRadius: 50,
    height: 80,
    width: 80,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#01e0f0',
    shadowOffset: { height: 0, width: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 20
  },
  successIconCircleGreen: {
    backgroundColor: '#c1f3d8'
  },
  successTitle: {
    color: '#0f242d',
    fontSize: fontSizes.titleMedium,
    fontWeight: '800',
    textAlign: 'center'
  },
  successSubtitle: {
    color: '#465359',
    fontSize: fontSizes.control,
    textAlign: 'center',
    marginTop: 8
  },
  referenceCard: {
    backgroundColor: '#f6f8f9',
    borderRadius: 8,
    padding: 16,
    marginTop: 24,
    gap: 16
  },
  referenceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  referenceLabel: {
    color: '#6e7a80',
    fontSize: fontSizes.control,
    fontWeight: '600'
  },
  referenceValue: {
    color: '#0f242d',
    fontSize: fontSizes.control,
    fontWeight: '700'
  },
  illustrationContainer: {
    backgroundColor: '#e6ebec',
    borderRadius: 12,
    marginTop: 24,
    overflow: 'hidden',
    height: 180,
    justifyContent: 'center',
    alignItems: 'center'
  },
  illustrationImage: {
    width: '100%',
    height: '100%',
    resizeMode: 'cover'
  },
  illustrationTitle: {
    color: '#0f242d',
    fontSize: fontSizes.titleSmall,
    fontWeight: '800',
    marginTop: 20
  },
  illustrationText: {
    color: '#465359',
    fontSize: fontSizes.control,
    lineHeight: 22,
    marginTop: 8
  },
  statusPill: {
    backgroundColor: '#01e0f0',
    borderRadius: 999,
    paddingHorizontal: 16,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 24,
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 8
  },
  statusPillText: {
    color: '#004a4f',
    fontSize: fontSizes.control,
    fontWeight: '700'
  },
  statusIndicator: {
    backgroundColor: '#01e0f0',
    borderRadius: 10,
    height: 10,
    width: 10
  },
  chargingActiveHeader: {
    alignItems: 'center',
    gap: 8,
    marginTop: 10
  },
  chargingActiveText: {
    color: '#00d588',
    fontSize: fontSizes.caption,
    fontWeight: '800',
    letterSpacing: 1
  },
  chargingStationName: {
    color: '#0f242d',
    fontSize: fontSizes.heading,
    fontWeight: '800',
    textAlign: 'center',
    lineHeight: 26
  },
  progressContainer: {
    alignItems: 'center',
    marginVertical: 32
  },
  progressRing: {
    alignItems: 'center',
    backgroundColor: '#dce7eb',
    borderRadius: 140,
    height: 240,
    justifyContent: 'center',
    width: 240,
    shadowColor: '#01e0f0',
    shadowOffset: { height: 0, width: 0 },
    shadowOpacity: 0.2,
    shadowRadius: 16
  },
  progressCircle: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderRadius: 112,
    height: 212,
    justifyContent: 'center',
    width: 212
  },
  progressPercent: {
    color: '#0f242d',
    fontSize: 54,
    fontWeight: '900',
    lineHeight: 60
  },
  progressLabel: {
    color: '#465359',
    fontSize: fontSizes.caption,
    fontWeight: '800',
    letterSpacing: 1,
    marginTop: 4
  },
  progressSublabel: {
    backgroundColor: '#eef2f3',
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 6,
    marginTop: 12
  },
  progressSublabelText: {
    color: '#0f242d',
    fontSize: fontSizes.tiny,
    fontWeight: '600'
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16
  },
  metricBlock: {
    flexBasis: '46%',
    flexGrow: 1
  },
  infoCard: {
    backgroundColor: '#dffbfc',
    borderColor: '#b7dfe2',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    padding: 16,
    gap: 12,
    marginTop: 16
  },
  infoCardText: {
    flex: 1,
    color: '#0f242d',
    fontSize: fontSizes.control,
    lineHeight: 22
  },
  dangerButton: {
    backgroundColor: '#be1a1e',
    borderRadius: 8,
    height: 56,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 10
  },
  dangerButtonText: {
    color: colors.white,
    fontSize: fontSizes.bodyLarge,
    fontWeight: '700'
  },
  totalAmountRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12
  },
  refundCard: {
    backgroundColor: '#dffbfc',
    borderColor: '#01e0f0',
    borderRadius: 8,
    borderWidth: 1,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12
  },
  refundCardText: {
    color: '#006c74',
    fontSize: fontSizes.bodyLarge,
    fontWeight: '800'
  },
  walletUpdateCard: {
    backgroundColor: '#fffdf4',
    borderColor: '#ffebb0',
    borderRadius: 8,
    borderWidth: 1,
    padding: 16,
    flexDirection: 'row',
    gap: 16,
    marginTop: 20
  },
  walletIconBadge: {
    alignItems: 'center',
    backgroundColor: '#ff9800',
    borderRadius: 6,
    height: 28,
    justifyContent: 'center',
    width: 28
  },
  walletUpdateTextWrap: {
    flex: 1,
    gap: 8
  },
  walletUpdateText: {
    color: '#955a15',
    fontSize: fontSizes.control,
    lineHeight: 20
  },
  walletBalanceText: {
    color: '#955a15',
    fontSize: fontSizes.control,
    fontWeight: '800'
  },
  backLink: {
    color: '#006c74',
    fontSize: fontSizes.control,
    fontWeight: '800',
    textAlign: 'center',
    letterSpacing: 1,
    marginTop: 16
  }
});
