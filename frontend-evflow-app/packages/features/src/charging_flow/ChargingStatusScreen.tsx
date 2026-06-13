import { useEffect, useMemo, useState } from 'react';
import { View, Text, Pressable, ScrollView } from 'react-native';
import { useLocation, useNavigate } from 'react-router';
import { chargingFlowStyles as styles } from '@evflow/ui';
import { fetchSpeedTiers, type SpeedTierApiItem } from '@evflow/shared';
import { ChargingFlowIcon } from './components/ChargingFlowIcon';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { ChargingFlowHeader } from './components/ChargingFlowHeader';
import { ProgressRing } from './components/ProgressRing';

const fastChargeTarget = 80;
const fastChargeDurationMs = 6000;
const slowChargeDurationMs = 10000;
const simulationTickMs = 100;
const FALLBACK_BASE_RATE_IDR = 2466; // only used if navigated here without a backend session

export function ChargingStatusScreen() {
  const navigate = useNavigate();
  const { state } = useLocation();
  const insets = useAppSafeAreaInsets();
  const [progress, setProgress] = useState(0);
  const [speedTiers, setSpeedTiers] = useState<SpeedTierApiItem[]>([]);

  const purchasedKwh = state?.energy || 20;
  const fastDeliveryPowerKw = state?.actualPowerKw || 142;
  const slowDeliveryPowerKw = Math.max(Math.floor(fastDeliveryPowerKw * 0.26), 1);
  const stationName = state?.station?.name || 'SPKLU PLN Sukses - Thamrin';
  const connectorType = state?.connector?.type || 'Connector 02';
  // Authoritative tariff the backend actually charged (deposit was computed from it).
  const pricePerKwh = state?.session?.base_rate_idr ?? FALLBACK_BASE_RATE_IDR;

  useEffect(() => {
    fetchSpeedTiers().then(setSpeedTiers).catch(console.error);
  }, []);

  useEffect(() => {
    const startedAt = Date.now();

    const interval = setInterval(() => {
      const elapsed = Date.now() - startedAt;

      if (elapsed <= fastChargeDurationMs) {
        setProgress((elapsed / fastChargeDurationMs) * fastChargeTarget);
        return;
      }

      const slowElapsed = elapsed - fastChargeDurationMs;
      const slowProgress = Math.min(slowElapsed / slowChargeDurationMs, 1);
      const nextProgress = fastChargeTarget + slowProgress * (100 - fastChargeTarget);

      setProgress(nextProgress);

      if (nextProgress >= 100) {
        clearInterval(interval);
        setProgress(100);
      }
    }, simulationTickMs);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (progress < 100) {
      return;
    }

    const timeout = setTimeout(() => {
      // Reached the purchased target: full energy delivered.
      navigate('/charging-flow/successful', { replace: true, state: { ...state, deliveredKwh: purchasedKwh } });
    }, 500);

    return () => clearTimeout(timeout);
  }, [navigate, progress, state, purchasedKwh]);

  const chargingMetrics = useMemo(() => {
    const roundedProgress = Math.min(Math.round(progress), 100);
    const deliveredKwh = (purchasedKwh * progress) / 100;
    const amountUtilized = Math.round(deliveredKwh * pricePerKwh);
    const isTapering = progress >= fastChargeTarget;
    const deliveryPower = isTapering ? slowDeliveryPowerKw : fastDeliveryPowerKw;
    
    const amps = Math.round((deliveryPower * 1000) / 400);
    const outputRate = `400V / ${amps}A`;

    const remainingMs =
      progress < fastChargeTarget
        ? ((fastChargeTarget - progress) / fastChargeTarget) * fastChargeDurationMs + slowChargeDurationMs
        : ((100 - progress) / (100 - fastChargeTarget)) * slowChargeDurationMs;
    const remainingMinutes = Math.max(Math.ceil(remainingMs / 60000), 0);

    const activeTier = speedTiers.find(tier => 
      deliveryPower >= tier.min_kw && (tier.max_kw === null || deliveryPower <= tier.max_kw)
    );
    const fallbackLabel = isTapering ? 'TAPERING CHARGE' : 'FAST CHARGE';
    const chargingLabel = activeTier ? activeTier.label : fallbackLabel;

    return {
      amountUtilized,
      deliveredKwh,
      deliveryPower,
      outputRate,
      remainingMinutes,
      roundedProgress,
      chargingLabel
    };
  }, [progress, purchasedKwh, fastDeliveryPowerKw, slowDeliveryPowerKw, speedTiers, pricePerKwh]);

  return (
    <View style={styles.page}>
      <ChargingFlowHeader
        title="Charging Status"
        onBack={() => navigate(-1)}
      />

      <ScrollView
        style={styles.scrollBody}
        contentContainerStyle={[styles.content, { paddingBottom: 40 + insets.bottom, paddingLeft: 24 + insets.left, paddingRight: 24 + insets.right }]}
        scrollIndicatorInsets={{ bottom: insets.bottom, left: insets.left, right: insets.right }}
      >
        <View style={styles.chargingActiveHeader}>
          <Text style={styles.chargingActiveText}>● CHARGING SESSION ACTIVE</Text>
          <Text style={styles.chargingStationName}>Station: {stationName} • {connectorType}</Text>
        </View>

        <View style={styles.progressContainer}>
          <ProgressRing progress={progress}>
            <Text style={styles.progressPercent}>{chargingMetrics.roundedProgress}%</Text>
            <Text style={styles.progressLabel}>
              {chargingMetrics.chargingLabel.toUpperCase()} CHARGING
            </Text>
            <View style={styles.progressSublabel}>
              <Text style={styles.progressSublabelText}>
                {chargingMetrics.deliveredKwh.toFixed(2)} / {purchasedKwh.toFixed(2)} kWh purchased
              </Text>
            </View>
          </ProgressRing>
        </View>

        <View style={styles.metricsGrid}>
          <View style={[styles.metricCard, styles.metricBlock]}>
            <View style={styles.metricValueRow}>
              <ChargingFlowIcon name="wallet" size={16} color="#019495" />
              <Text style={[styles.metricLabel, { fontSize: 10 }]}>AMOUNT UTILIZED</Text>
            </View>
            <Text style={styles.metricValue}>Rp {chargingMetrics.amountUtilized.toLocaleString('id-ID')}</Text>
          </View>
          
          <View style={[styles.metricCard, styles.metricBlock]}>
            <View style={styles.metricValueRow}>
              <ChargingFlowIcon name="timer" size={16} color="#019495" />
              <Text style={[styles.metricLabel, { fontSize: 10 }]}>EST. TIME LEFT</Text>
            </View>
            <Text style={[styles.metricValue, { lineHeight: 28 }]}>
              {chargingMetrics.remainingMinutes} min{chargingMetrics.remainingMinutes === 1 ? '' : 's'} remaining
            </Text>
          </View>
          
          <View style={[styles.metricCard, styles.metricBlock]}>
            <View style={styles.metricValueRow}>
              <ChargingFlowIcon name="lightning" size={16} color="#019495" />
              <Text style={[styles.metricLabel, { fontSize: 10 }]}>DELIVERY POWER</Text>
            </View>
            <Text style={styles.metricValue}>{chargingMetrics.deliveryPower} kW</Text>
          </View>
          
          <View style={[styles.metricCard, styles.metricBlock]}>
            <View style={styles.metricValueRow}>
              <ChargingFlowIcon name="connector" size={16} color="#019495" />
              <Text style={[styles.metricLabel, { fontSize: 10 }]}>OUTPUT RATE</Text>
            </View>
            <Text style={[styles.metricValue, { lineHeight: 28 }]}>{chargingMetrics.outputRate}</Text>
          </View>
        </View>

        <View style={styles.infoCard}>
          <Text style={{ fontSize: 20, color: '#019495', marginTop: 2 }}>ⓘ</Text>
          <Text style={styles.infoCardText}>
            Your charging session will automatically pause once it hits your purchased target of {purchasedKwh.toFixed(2)} kWh to protect battery health.
          </Text>
        </View>

        <View style={styles.footerSpacer} />

        <View style={styles.footerAction}>
          <Pressable
            style={styles.dangerButton}
            onPress={() => navigate('/charging-flow/successful', {
              state: { ...state, deliveredKwh: (purchasedKwh * progress) / 100 }
            })}
          >
            <ChargingFlowIcon name="stop" size={20} color="#ffffff" />
            <Text style={styles.dangerButtonText}>STOP CHARGING SESSION</Text>
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}
