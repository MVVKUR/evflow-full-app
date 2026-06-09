import { View, Text, Pressable, ScrollView, Image, type ImageSourcePropType } from 'react-native';
import { useLocation, useNavigate } from 'react-router';
import { chargingFlowStyles as styles } from '@evflow/ui';
import { ChargingFlowIcon } from './components/ChargingFlowIcon';
import chargingCompleteTickPng from '../assets/images/charging-complete-tick.png';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { ChargingFlowHeader } from './components/ChargingFlowHeader';
import { downloadReceipt } from '../shared/downloadReceipt';

const BASE_RATE = 2466;
const ADMIN_FEE = 2500;
const INITIAL_BALANCE = 250000;

export function ChargingSuccessfulScreen() {
  const navigate = useNavigate();
  const { state } = useLocation();
  const insets = useAppSafeAreaInsets();

  const purchasedKwh = state?.energy || 20;
  const initialDeposit = state?.totalDue || (purchasedKwh * BASE_RATE + ADMIN_FEE);
  const stationName = state?.station?.name || 'SPKLU PLN Sukses';

  // Simulate stopping slightly before 100% just for the refund demonstration,
  // or use exactly purchasedKwh if it's small.
  const deliveredKwh = Math.max(purchasedKwh * 0.825, 0.1); 
  const actualCost = Math.round(deliveredKwh * BASE_RATE) + ADMIN_FEE;
  const refundAmount = Math.max(initialDeposit - actualCost, 0);
  const updatedBalance = INITIAL_BALANCE - initialDeposit + refundAmount;

  return (
    <View style={styles.page}>
      <ChargingFlowHeader
        title="Charging Successful"
        onBack={() => navigate(-1)}
      />

      <ScrollView
        style={styles.scrollBody}
        contentContainerStyle={[styles.content, { paddingBottom: 40 + insets.bottom, paddingLeft: 24 + insets.left, paddingRight: 24 + insets.right }]}
        scrollIndicatorInsets={{ bottom: insets.bottom, left: insets.left, right: insets.right }}
      >
        <View style={styles.successIconWrap}>
          <Image source={chargingCompleteTickPng as unknown as ImageSourcePropType} style={{ width: 80, height: 80 }} />
        </View>

        <View style={{ marginBottom: 16 }}>
          <Text style={styles.successTitle}>Charging Successful</Text>
          <Text style={styles.successSubtitle}>Session ended securely • Station: {stationName}</Text>
        </View>

        <View style={styles.metricsRow}>
          <View style={styles.metricCard}>
            <Text style={styles.metricLabel}>TOTAL ENERGY DELIVERED</Text>
            <View style={styles.metricValueRow}>
              <Text style={styles.metricValue}>{deliveredKwh.toFixed(2)}</Text>
              <Text style={{ fontSize: 14, color: '#465359', fontWeight: '700', marginTop: 4 }}>kWh</Text>
            </View>
          </View>
          <View style={styles.metricCard}>
            <Text style={styles.metricLabel}>CHARGING DURATION</Text>
            <View style={styles.metricValueRow}>
              <Text style={styles.metricValue}>{Math.ceil(purchasedKwh * 1.1)}</Text>
              <Text style={{ fontSize: 14, color: '#465359', fontWeight: '700', marginTop: 4, marginRight: 4 }}>m</Text>
              <Text style={styles.metricValue}>14</Text>
              <Text style={{ fontSize: 14, color: '#465359', fontWeight: '700', marginTop: 4 }}>s</Text>
            </View>
          </View>
        </View>

        <View style={styles.summaryCard}>
          <View style={[styles.metricValueRow, { marginBottom: 16, borderBottomWidth: 1, borderBottomColor: '#dee4e6', paddingBottom: 16, gap: 6 }]}>
            <ChargingFlowIcon name="receipt" size={16} />
            <Text style={styles.metricLabel}>TRANSACTION SETTLEMENT</Text>
          </View>
          
          <View style={styles.summaryRow}>
            <Text style={styles.summaryLabel}>Initial Deposit (for {purchasedKwh.toFixed(2)} kWh)</Text>
            <Text style={styles.summaryLabel}>Rp {initialDeposit.toLocaleString('id-ID')}</Text>
          </View>
          
          <View style={styles.totalAmountRow}>
            <Text style={styles.summaryLabel}>Actual Cost (for {deliveredKwh.toFixed(2)} kWh)</Text>
            <Text style={styles.totalLabel}>Rp {actualCost.toLocaleString('id-ID')}</Text>
          </View>

          <View style={styles.refundCard}>
            <ChargingFlowIcon name="piggy" size={24} />
            <Text style={styles.refundCardText}>Refund Amount Rp {refundAmount.toLocaleString('id-ID')}</Text>
          </View>
        </View>

        <View style={styles.walletUpdateCard}>
          <View style={styles.walletIconBadge}>
            <ChargingFlowIcon name="wallet_bg" size={16} color="#ffffff" />
          </View>
          <View style={styles.walletUpdateTextWrap}>
            <Text style={styles.walletUpdateText}>
              Unused kWh balance has been instantly credited back to your <Text style={{ fontWeight: '800' }}>EV-Wallet</Text>.
            </Text>
            <Text style={styles.metricLabel}>
              <Text style={{ color: '#955a15' }}>UPDATED BALANCE:</Text> <Text style={{ color: '#955a15', fontSize: 16 }}>Rp {updatedBalance.toLocaleString('id-ID')}</Text>
            </Text>
          </View>
        </View>

        <View style={styles.footerSpacer} />

        <View style={styles.footerAction}>
          <Pressable style={styles.primaryButton} onPress={() => downloadReceipt({
            amount: `Rp ${actualCost.toLocaleString('id-ID')}`,
            date: new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Jakarta' }).format(new Date()),
            destination: stationName,
            orderId: `EVFLOW-${Math.floor(Math.random() * 1000000)}`,
            status: 'Success',
            summaryMeta: `REF-${Math.floor(Math.random() * 1000000)}`,
            summaryTitle: 'Charging Payment',
            time: new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' }).format(new Date()),
            total: `Rp ${actualCost.toLocaleString('id-ID')}`,
            transactionId: `TXN-${Math.floor(Math.random() * 1000000)}`,
            typeText: 'Charging'
          })}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
              <Text style={styles.primaryButtonText}>VIEW CONSOLIDATED RECEIPT</Text>
              <ChargingFlowIcon name="download" size={16} color="#004a4f" />
            </View>
          </Pressable>
          <Pressable onPress={() => navigate('/ev-driver/map')}>
            <Text style={styles.backLink}>BACK TO MAP DISCOVERY</Text>
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}
