import { useCallback, useEffect, useState } from 'react';
import { View, Text, Pressable, ScrollView, Image, ActivityIndicator, type ImageSourcePropType } from 'react-native';
import { useLocation, useNavigate } from 'react-router';
import { chargingFlowStyles as styles } from '@evflow/ui';
import { settleChargingSession, type ChargingSessionApiResponse } from '@evflow/shared';
import { ChargingFlowIcon } from './components/ChargingFlowIcon';
import chargingCompleteTickPng from '../assets/images/charging-complete-tick.png';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { ChargingFlowHeader } from './components/ChargingFlowHeader';
import { downloadReceipt } from '../shared/downloadReceipt';

export function ChargingSuccessfulScreen() {
  const navigate = useNavigate();
  const { state } = useLocation();
  const insets = useAppSafeAreaInsets();

  const session = state?.session as ChargingSessionApiResponse | undefined;
  const deliveredKwhInput: number = state?.deliveredKwh ?? session?.energy_kwh ?? state?.energy ?? 0;

  const [settlement, setSettlement] = useState<ChargingSessionApiResponse | null>(null);
  const [settling, setSettling] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // settle is idempotent on the backend, so retries / re-mounts never double-credit.
  const runSettle = useCallback(async () => {
    if (!session?.id) {
      setSettling(false);
      setError('This charging session is no longer available. Please return to the map.');
      return;
    }
    setSettling(true);
    setError(null);
    try {
      const result = await settleChargingSession(session.id, deliveredKwhInput);
      setSettlement(result);
    } catch (err) {
      console.error('Failed to settle charging session:', err);
      setError('Could not settle the session. Please retry.');
    } finally {
      setSettling(false);
    }
  }, [session?.id, deliveredKwhInput]);

  useEffect(() => { runSettle(); }, [runSettle]);

  const stationName = settlement?.station_name || session?.station_name || state?.station?.name || 'SPKLU PLN Sukses';
  const purchasedKwh = settlement?.energy_kwh ?? session?.energy_kwh ?? state?.energy ?? 0;
  const deliveredKwh = settlement?.delivered_kwh ?? deliveredKwhInput;
  const initialDeposit = settlement?.deposit_idr ?? session?.deposit_idr ?? 0;
  const actualCost = settlement?.actual_cost_idr ?? 0;
  const refundAmount = settlement?.refund_idr ?? 0;
  const updatedBalance = settlement?.wallet_balance_idr ?? 0;
  const referenceId = (settlement?.id ?? session?.id ?? '').slice(0, 8).toUpperCase();

  if (settling) {
    return (
      <View style={[styles.page, { justifyContent: 'center', alignItems: 'center' }]}>
        <ActivityIndicator size="large" color="#00696F" />
        <Text style={{ marginTop: 16, color: '#6B7A7B' }}>Settling your session…</Text>
      </View>
    );
  }

  if (error && !settlement) {
    return (
      <View style={styles.page}>
        <ChargingFlowHeader title="Charging Successful" onBack={() => navigate(-1)} />
        <View style={[styles.content, { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 16 }]}>
          <Text style={{ color: '#ba1a1a', fontSize: 14, textAlign: 'center' }}>{error}</Text>
          {session?.id ? (
            <Pressable style={styles.primaryButton} onPress={runSettle}>
              <Text style={styles.primaryButtonText}>RETRY SETTLEMENT</Text>
            </Pressable>
          ) : null}
          <Pressable onPress={() => navigate('/ev-driver/map')}>
            <Text style={styles.backLink}>BACK TO MAP DISCOVERY</Text>
          </Pressable>
        </View>
      </View>
    );
  }

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
            orderId: `EVFLOW-${referenceId}`,
            status: 'Success',
            summaryMeta: `REF-${referenceId}`,
            summaryTitle: 'Charging Payment',
            time: new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' }).format(new Date()),
            total: `Rp ${actualCost.toLocaleString('id-ID')}`,
            transactionId: `TXN-${referenceId}`,
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
