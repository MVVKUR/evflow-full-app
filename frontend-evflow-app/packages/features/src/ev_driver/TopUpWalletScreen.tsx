import { useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { useLocation, useNavigate } from 'react-router';
import { createWalletTopup, fetchWalletBalance, fetchWalletTopup } from '@evflow/shared';
import { walletScreenStyles as styles } from '@evflow/ui';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';

type TopUpWalletScreenProps = {
  bottomOffset?: number;
  topInset?: number;
};

const minimumTopup = 10000;

export function TopUpWalletScreen({ bottomOffset = 0, topInset = 0 }: TopUpWalletScreenProps) {
  const navigate = useNavigate();
  const [amount, setAmount] = useState('');
  const [balance, setBalance] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const parsedAmount = parseAmount(amount);
  const canSubmit = parsedAmount >= minimumTopup && !submitting;

  useEffect(() => {
    let mounted = true;

    fetchWalletBalance()
      .then((wallet) => {
        if (mounted) {
          setBalance(wallet.balance_idr);
        }
      })
      .catch((err) => {
        console.error('Unable to fetch wallet balance', err);
      });

    return () => {
      mounted = false;
    };
  }, []);

  const handleTopUp = () => {
    if (!canSubmit) {
      setError(`Minimal top up ${formatCurrency(minimumTopup)}`);
      return;
    }

    setSubmitting(true);
    setError(null);

    createWalletTopup(parsedAmount)
      .then((topup) => {
        // Send the user to the Xendit checkout; the waiting screen polls until it is paid
        // and also offers a button to reopen the page if a popup blocker ate this one.
        if (topup.invoice_url) {
          Linking.openURL(topup.invoice_url).catch((err) => {
            console.error('Unable to open the payment page', err);
          });
        }
        navigate('/ev-driver/wallet/topup/success', {
          state: {
            amountIdr: topup.amount_idr,
            invoiceUrl: topup.invoice_url,
            topupId: topup.topup_id
          }
        });
      })
      .catch((err) => {
        console.error('Unable to create wallet top-up', err);
        setError('Top up could not be started. Please try again.');
      })
      .finally(() => setSubmitting(false));
  };

  return (
    <View style={styles.page}>
      <WalletFlowHeader title="Top Up Wallet" topInset={topInset} onBack={() => navigate('/ev-driver/wallet')} />

      <ScrollView
        contentContainerStyle={[styles.topupContent, { paddingBottom: 32 + bottomOffset }]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.topupBalanceCard}>
          <View>
            <Text style={styles.topupBalanceLabel}>Saldo Saat Ini</Text>
            <Text style={styles.topupBalanceValue}>{formatCurrency(balance)}</Text>
          </View>
          <View style={styles.topupWalletBadge}>
            <SvgAssetIcon color="#ffffff" height={34} name="lightning" width={30} />
            <View style={styles.topupCurrencyBubble}>
              <Text style={styles.topupCurrencyText}>Rp</Text>
            </View>
          </View>
        </View>

        <View style={styles.topupFormSection}>
          <Text style={styles.topupSectionTitle}>Input Saldo</Text>
          <View style={styles.topupInputWrap}>
            <Text style={styles.topupPrefix}>Rp</Text>
            <TextInput
              keyboardType="numeric"
              onChangeText={(value) => {
                setAmount(formatNumericInput(value));
                setError(null);
              }}
              placeholder="Masukkan nominal"
              placeholderTextColor="#c6cedb"
              style={styles.topupInput}
              value={amount}
            />
          </View>
          <View style={styles.topupHelperRow}>
            <View style={styles.topupInfoIcon}>
              <Text style={styles.topupInfoIconText}>i</Text>
            </View>
            <Text style={[styles.topupHelperText, error ? styles.topupErrorText : null]}>
              {error ?? `Minimal top up ${formatCurrency(minimumTopup)}`}
            </Text>
          </View>
        </View>

        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: !canSubmit }}
          disabled={!canSubmit}
          onPress={handleTopUp}
          style={[styles.topupPrimaryButton, !canSubmit && styles.topupDisabledButton]}
        >
          <SvgAssetIcon color="#ffffff" height={22} name="bankTopup" width={24} />
          <Text style={styles.topupPrimaryButtonText}>{submitting ? 'Processing...' : 'Top Up'}</Text>
        </Pressable>

        <View style={styles.topupTrustCard}>
          <View style={styles.topupTrustIcon}>
            <SvgAssetIcon color="#00b8b0" height={30} name="tick" width={30} />
          </View>
          <View style={styles.topupTrustTextWrap}>
            <Text style={styles.topupTrustTitle}>Aman & Terpercaya</Text>
            <Text style={styles.topupTrustText}>Top up saldo Anda aman dan diproses secara instan.</Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

export function TopUpSuccessScreen({ bottomOffset = 0, topInset = 0 }: TopUpWalletScreenProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as { amountIdr?: number; invoiceUrl?: string; topupId?: string } | null;
  // In-app flow passes the id via navigation state; the Xendit success redirect
  // lands here with ?topup_id=... and no state.
  const topupId = state?.topupId ?? parseTopupIdFromSearch(location.search);
  const invoiceUrl = state?.invoiceUrl ?? null;
  const [paid, setPaid] = useState(false);
  const [amount, setAmount] = useState(state?.amountIdr ?? 0);

  useEffect(() => {
    if (!topupId || paid) {
      return;
    }

    let mounted = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = () => {
      fetchWalletTopup(topupId)
        .then((topup) => {
          if (!mounted) {
            return;
          }
          setAmount(topup.amount_idr);
          if (topup.status === 'paid') {
            setPaid(true);
          } else {
            timer = setTimeout(poll, 3000);
          }
        })
        .catch((err) => {
          console.error('Unable to check top-up status', err);
          if (mounted) {
            timer = setTimeout(poll, 5000);
          }
        });
    };

    poll();

    return () => {
      mounted = false;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [topupId, paid]);

  const waiting = Boolean(topupId) && !paid;

  return (
    <View style={styles.page}>
      <WalletFlowHeader
        title={waiting ? 'Menunggu Pembayaran' : 'Top Up Success'}
        topInset={topInset}
        titleStyle={styles.topupSuccessHeaderTitle}
        onBack={() => navigate('/ev-driver/wallet/topup')}
      />

      <View style={[styles.topupSuccessContent, { paddingBottom: 32 + bottomOffset }]}>
        <View style={styles.topupSuccessMarkWrap}>
          {waiting ? (
            <ActivityIndicator color="#00b8b0" size="large" />
          ) : (
            <>
              <View style={styles.topupSuccessMark}>
                <Text style={styles.topupSuccessCheck}>✓</Text>
              </View>
              <View style={styles.topupConfettiDotLarge} />
              <View style={styles.topupConfettiDotSmall} />
              <View style={styles.topupConfettiDotTiny} />
            </>
          )}
        </View>

        <Text style={styles.topupSuccessTitle}>{waiting ? 'Menunggu Pembayaran' : 'Top Up Successful'}</Text>
        <Text style={styles.topupSuccessAmount}>{formatCurrency(amount)}</Text>
        <Text style={styles.topupSuccessSubtitle}>
          {waiting
            ? 'Selesaikan pembayaran di halaman Xendit. Saldo akan terisi otomatis setelah pembayaran diterima.'
            : 'Your wallet has been topped up successfully.'}
        </Text>

        {waiting && invoiceUrl ? (
          <Pressable
            accessibilityRole="button"
            onPress={() => {
              Linking.openURL(invoiceUrl).catch((err) => console.error('Unable to open the payment page', err));
            }}
            style={styles.topupPrimaryButton}
          >
            <Text style={styles.topupPrimaryButtonText}>Buka Halaman Pembayaran</Text>
          </Pressable>
        ) : null}

        <View style={styles.topupSuccessSpacer} />

        <Pressable accessibilityRole="button" onPress={() => navigate('/ev-driver/wallet')} style={styles.topupDoneButton}>
          <Text style={styles.topupDoneButtonText}>{waiting ? 'Kembali ke Wallet' : 'Done'}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function parseTopupIdFromSearch(search: string) {
  const match = /[?&]topup_id=([^&]+)/.exec(search);
  return match ? decodeURIComponent(match[1]) : undefined;
}

type WalletFlowHeaderProps = {
  title: string;
  topInset: number;
  titleStyle?: object;
  onBack: () => void;
};

function WalletFlowHeader({ title, titleStyle, topInset, onBack }: WalletFlowHeaderProps) {
  return (
    <View style={[styles.topupHeader, { paddingTop: topInset }]}>
      <Pressable accessibilityLabel="Back" accessibilityRole="button" onPress={onBack} style={styles.topupBackButton}>
        <SvgAssetIcon color="#191C1D" height={20} name="leftChevron" width={13} />
      </Pressable>
      <Text numberOfLines={1} style={[styles.topupHeaderTitle, titleStyle]}>
        {title}
      </Text>
      <View style={styles.topupHeaderSpacer} />
    </View>
  );
}

function parseAmount(value: string) {
  return Number(value.replace(/\D/g, '')) || 0;
}

function formatNumericInput(value: string) {
  const numeric = value.replace(/\D/g, '');
  return numeric ? Number(numeric).toLocaleString('id-ID') : '';
}

function formatCurrency(amount: number) {
  return `Rp ${Math.abs(amount).toLocaleString('id-ID')}`;
}
