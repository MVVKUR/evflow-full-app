import { Modal, Platform, Pressable, ScrollView, Text, View, useWindowDimensions } from 'react-native';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { walletScreenStyles as styles } from '@evflow/ui';
import { AuthRequiredError, fetchWalletBalance, fetchWalletTopups, fetchChargingSessions, formatTransactionDate, type TopupApiItem, type ChargingSessionApiResponse } from '@evflow/shared';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';
import { type WalletTransaction } from './walletTransactions';
import { downloadReceipt } from '../shared/downloadReceipt';
import { ReceiptPdfViewer } from '../shared/ReceiptPdfViewer';

type WalletScreenProps = {
  bottomInset?: number;
  bottomOffset?: number;
  topInset?: number;
};

const historyPinOffset = 108;
type TransactionSort = 'date_desc' | 'date_asc' | 'amount_desc' | 'amount_asc' | 'status';
const sortOptions: { value: TransactionSort; label: string }[] = [
  { value: 'date_desc', label: 'Newest first' },
  { value: 'date_asc', label: 'Oldest first' },
  { value: 'amount_desc', label: 'Amount high' },
  { value: 'amount_asc', label: 'Amount low' },
  { value: 'status', label: 'Status' }
];

export function WalletScreen({ bottomInset = 0, bottomOffset = 0, topInset = 0 }: WalletScreenProps) {
  const navigate = useNavigate();
  const { height, width } = useWindowDimensions();
  const [balance, setBalance] = useState<number | null>(null);
  const [apiTopups, setApiTopups] = useState<TopupApiItem[]>([]);
  const [apiSessions, setApiSessions] = useState<ChargingSessionApiResponse[]>([]);
  const [selectedTransaction, setSelectedTransaction] = useState<WalletTransaction | null>(null);
  const [isHistoryPinned, setIsHistoryPinned] = useState(false);
  const [sortOrder, setSortOrder] = useState<TransactionSort>('date_desc');
  const [sortOpen, setSortOpen] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const desktop = width >= 768;
  const transactions = useMemo(
    () => sortTransactions([...apiTopups.map(mapTopupToTransaction), ...apiSessions.map(mapSessionToTransaction)], sortOrder),
    [apiTopups, apiSessions, sortOrder]
  );
  const selectedSortLabel = sortOptions.find((option) => option.value === sortOrder)?.label ?? 'Sort';

  useEffect(() => {
    let mounted = true;

    fetchWalletBalance()
      .then((wallet) => {
        if (mounted) {
          setBalance(wallet.balance_idr);
        }
      })
      .catch((error) => {
        if (mounted) {
          setLoadError(error instanceof AuthRequiredError ? error.message : 'Unable to load wallet balance.');
        }
      });

    fetchWalletTopups()
      .then((topups) => {
        if (mounted) {
          setApiTopups(topups);
        }
      })
      .catch((error) => {
        if (mounted) {
          setLoadError(error instanceof AuthRequiredError ? error.message : 'Unable to load wallet top-ups.');
        }
      });

    fetchChargingSessions()
      .then((sessions) => {
        if (mounted) {
          setApiSessions(sessions);
        }
      })
      .catch((error) => {
        if (mounted) {
          setLoadError(error instanceof AuthRequiredError ? error.message : 'Unable to load charging sessions.');
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  return (
    <View style={styles.page}>
      <ScrollView
        contentContainerStyle={[
          styles.content,
          {
            paddingBottom: 28 + bottomOffset,
            paddingTop: 24 + topInset
          }
        ]}
        onScroll={(event) => {
          const shouldPinHistory = event.nativeEvent.contentOffset.y >= historyPinOffset;
          setIsHistoryPinned((current) => (current === shouldPinHistory ? current : shouldPinHistory));
        }}
        scrollEventThrottle={16}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.balanceCard}>
          <View>
            <Text style={styles.balanceLabel}>Total Balance</Text>
            <Text style={styles.balanceValue}>{balance === null ? 'Rp …' : formatCurrency(balance)}</Text>
          </View>
          <Pressable accessibilityRole="button" onPress={() => navigate('/ev-driver/wallet/topup')} style={styles.topUpButton}>
            <Text style={styles.topUpButtonText}>Top Up</Text>
          </Pressable>
        </View>

        <View style={styles.historyHeader}>
          <Text style={styles.historyTitle}>Transaction History</Text>
          <Pressable accessibilityRole="button" onPress={() => setSortOpen((current) => !current)} style={styles.filterButton}>
            <SvgAssetIcon color="#1f2529" height={12} name="sort" width={18} />
          </Pressable>
        </View>
        <Text style={{ color: '#53606a', fontSize: 12, fontWeight: '700', marginTop: -10 }}>Sorted: {selectedSortLabel}</Text>
        {sortOpen ? <SortMenu selected={sortOrder} onSelect={(nextSort) => {
          setSortOrder(nextSort);
          setSortOpen(false);
        }} /> : null}

        <View style={styles.transactionList}>
          {loadError ? <Text style={styles.transactionMeta}>{loadError}</Text> : null}
          {!loadError && transactions.length === 0 ? <Text style={styles.transactionMeta}>No transactions yet.</Text> : null}
          {!loadError ? transactions.map((transaction) => (
            <TransactionRow
              key={transaction.id}
              transaction={transaction}
              onPress={() => setSelectedTransaction(transaction)}
            />
          )) : null}
        </View>
      </ScrollView>

      {isHistoryPinned ? (
        <View pointerEvents="box-none" style={styles.pinnedHistoryShell}>
          <View style={[styles.pinnedHistoryInner, { paddingTop: topInset }]}>
            <View style={styles.historyHeader}>
              <Text style={styles.historyTitle}>Transaction History</Text>
              <Pressable accessibilityRole="button" onPress={() => setSortOpen((current) => !current)} style={styles.filterButton}>
                <SvgAssetIcon color="#1f2529" height={12} name="sort" width={18} />
              </Pressable>
            </View>
          </View>
        </View>
      ) : null}

      <TransactionDetailModal
        bottomInset={bottomInset}
        desktop={desktop}
        screenHeight={height}
        topInset={topInset}
        transaction={selectedTransaction}
        onClose={() => setSelectedTransaction(null)}
      />
    </View>
  );
}

type SortMenuProps = {
  selected: TransactionSort;
  onSelect: (sort: TransactionSort) => void;
};

function SortMenu({ selected, onSelect }: SortMenuProps) {
  return (
    <View style={{ backgroundColor: '#ffffff', borderColor: '#e0e6ea', borderRadius: 8, borderWidth: 1, gap: 2, padding: 6 }}>
      {sortOptions.map((option) => (
        <Pressable
          accessibilityRole="button"
          key={option.value}
          onPress={() => onSelect(option.value)}
          style={{ backgroundColor: selected === option.value ? '#e9fbfc' : '#ffffff', borderRadius: 6, minHeight: 36, justifyContent: 'center', paddingHorizontal: 10 }}
        >
          <Text style={{ color: '#151c2a', fontSize: 13, fontWeight: selected === option.value ? '900' : '700' }}>{option.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

type TransactionRowProps = {
  transaction: WalletTransaction;
  onPress: () => void;
};

function TransactionRow({ transaction, onPress }: TransactionRowProps) {
  const success = transaction.status === 'success';

  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.transactionCard}>
      <View style={[styles.transactionIcon, transaction.status === 'failed' && styles.failedTransactionIcon]}>
        <SvgAssetIcon
          color={transaction.status === 'failed' ? '#93000A' : '#53686A'}
          height={transaction.status === 'failed' ? 19 : 20}
          name={getTransactionIconName(transaction)}
          width={transaction.status === 'failed' ? 22 : 20}
        />
      </View>

      <View style={styles.transactionBody}>
        <Text style={styles.transactionTitle}>{transaction.title}</Text>
        <Text style={styles.transactionMeta}>
          {transaction.description}
          {transaction.connectorType ? ` • ${transaction.connectorType}` : ` • ${transaction.referenceNo}`}
        </Text>
      </View>

      <View style={styles.transactionAmountWrap}>
        <Text style={[styles.transactionAmount, transaction.amount > 0 && styles.positiveAmount]}>
          {formatSignedCurrency(transaction.amount)}
        </Text>
        <View style={[styles.statusBadge, !success && styles.failedStatusBadge]}>
          <Text style={[styles.statusBadgeText, !success && styles.failedStatusBadgeText]}>
            {success ? 'SUCCESS' : 'FAILED'}
          </Text>
        </View>
      </View>
    </Pressable>
  );
}

type TransactionDetailModalProps = {
  bottomInset: number;
  desktop: boolean;
  screenHeight: number;
  topInset: number;
  transaction: WalletTransaction | null;
  onClose: () => void;
};

function TransactionDetailModal({ bottomInset, desktop, screenHeight, topInset, transaction, onClose }: TransactionDetailModalProps) {
  const [detailsExpanded, setDetailsExpanded] = useState(true);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [downloadMessage, setDownloadMessage] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  if (!transaction) {
    return null;
  }

  const currentTransaction = transaction;
  const success = transaction.status === 'success';
  const receiptData = {
    amount: formatDetailAmount(transaction.amount),
    date: formatDate(transaction.occurredAt),
    destination: transaction.destination,
    orderId: transaction.orderId,
    energyKwh: transaction.energyKwh ? `${transaction.energyKwh.toFixed(2)} kWh` : undefined,
    paymentMethod: transaction.paymentMethod ?? (transaction.type === 'topup' ? 'Xendit' : 'EV-Wallet'),
    status: success ? 'Success' : 'Failed',
    summaryMeta: transaction.referenceNo,
    summaryTitle: transaction.type === 'topup' ? 'Wallet Topup' : 'Charging Payment',
    time: formatTime(transaction.occurredAt),
    total: formatCurrency(Math.abs(transaction.amount)),
    transactionId: transaction.referenceNo,
    typeText: transaction.type === 'topup' ? 'Top Up' : 'Charging'
  };

  async function handleDownloadInvoice() {
    if (downloading) {
      return;
    }

    setDownloading(true);
    setDownloadMessage(null);
    const downloaded = await downloadReceipt(receiptData);
    setDownloadMessage(downloaded ? 'Invoice downloaded.' : 'Invoice download failed. Please try again.');
    setDownloading(false);
  }

  async function handleCopyReference() {
    const copied = await copyToClipboard(currentTransaction.referenceNo);
    setCopyMessage(copied ? 'Copied.' : 'Copy failed. Please copy manually.');
  }

  return (
    <Modal animationType={desktop ? 'fade' : 'slide'} transparent visible onRequestClose={onClose}>
      <View style={[styles.modalOverlay, desktop ? styles.centeredModalOverlay : styles.bottomModalOverlay]}>
        <View
          style={[
            styles.detailSheet,
            desktop ? [styles.desktopDetailSheet, { height: Math.floor(screenHeight * 0.8) }] : styles.mobileDetailSheet
          ]}
        >
          <View style={[styles.detailHeader, !desktop && { paddingTop: topInset }]}>
            <Pressable accessibilityLabel="Close transaction details" accessibilityRole="button" onPress={onClose} style={styles.closeButton}>
              <SvgAssetIcon color="#1f2529" height={14} name="close" width={14} />
            </Pressable>
            <Text style={styles.detailHeaderTitle}>Transaction Details</Text>
            <View style={styles.closeButton} />
          </View>

          <ScrollView contentContainerStyle={styles.detailContent} showsVerticalScrollIndicator={false}>
            <View style={[styles.detailResultIcon, !success && styles.failedDetailResultIcon]}>
              <Text style={[styles.detailResultIconText, !success && styles.failedDetailResultIconText]}>
                {success ? '✓' : '!'}
              </Text>
            </View>
            <Text style={styles.detailAmount}>{formatDetailAmount(transaction.amount)}</Text>
            <Text style={styles.detailType}>{transaction.type === 'topup' ? 'Top Up' : 'Charging'}</Text>

            <View style={styles.detailSummaryCard}>
              <View style={styles.detailSummaryIcon}>
                <SvgAssetIcon color="#53686A" height={20} name={transaction.type === 'topup' ? 'bankTopup' : 'chargingHistory'} width={20} />
              </View>
              <View>
                <Text style={styles.detailSummaryTitle}>
                  {transaction.type === 'topup' ? 'Wallet Topup' : 'Charging Payment'}
                </Text>
                <Text style={styles.detailSummaryMeta}>{transaction.referenceNo}</Text>
              </View>
            </View>
            <Pressable
              accessibilityRole="button"
              onPress={handleCopyReference}
              style={{ alignItems: 'center', alignSelf: 'flex-start', borderColor: '#d8e1e7', borderRadius: 8, borderWidth: 1, minHeight: 36, justifyContent: 'center', marginTop: 12, paddingHorizontal: 12 }}
            >
              <Text style={{ color: '#00696f', fontSize: 13, fontWeight: '900' }}>Copy Reference</Text>
            </Pressable>
            {copyMessage ? <Text style={{ color: copyMessage === 'Copied.' ? '#006c4f' : '#b32126', fontSize: 12, fontWeight: '700', marginTop: 8 }}>{copyMessage}</Text> : null}

            <Pressable
              accessibilityRole="button"
              accessibilityState={{ expanded: detailsExpanded }}
              onPress={() => setDetailsExpanded((current) => !current)}
              style={styles.detailSectionHeader}
            >
              <Text style={styles.detailSectionTitle}>TRANSACTION DETAILS</Text>
              <Text style={[styles.detailChevron, !detailsExpanded && { transform: [{ rotate: '180deg' }] }]}>⌃</Text>
            </Pressable>

            {detailsExpanded ? (
              <>
                <DetailRow label="Status" value={success ? 'Success' : 'Failed'} valueStyle={success ? styles.successText : styles.failedText} />
                <DetailRow label="Added To" value={transaction.destination} valueStyle={styles.detailStrongValue} />
                <DetailRow label="Time" value={formatTime(transaction.occurredAt)} valueStyle={styles.detailStrongValue} />
                <DetailRow label="Date" value={formatDate(transaction.occurredAt)} valueStyle={styles.detailStrongValue} />
                <DetailRow label="Transaction ID" value={transaction.referenceNo} />
                <DetailRow label="Order ID" value={transaction.orderId} valueStyle={styles.detailStrongValue} />

                <View style={styles.detailDivider} />
                <DetailRow label="Amount" value={formatCurrency(Math.abs(transaction.amount))} valueStyle={styles.detailStrongValue} />
                <DetailRow label="Total" value={formatCurrency(Math.abs(transaction.amount))} valueStyle={styles.detailTotalValue} labelStyle={styles.detailTotalLabel} />
              </>
            ) : null}
          </ScrollView>

          <View style={[styles.invoiceFooter, { paddingBottom: 24 + bottomInset }]}>
            <Pressable accessibilityRole="button" style={styles.invoiceButton} onPress={handleDownloadInvoice}>
              <Text style={styles.invoiceButtonText}>{downloading ? 'Downloading...' : 'Download Invoice'}</Text>
            </Pressable>
            {downloadMessage ? <Text style={{ color: downloadMessage.includes('failed') ? '#b32126' : '#006c4f', fontSize: 12, fontWeight: '700', marginTop: 8, textAlign: 'center' }}>{downloadMessage}</Text> : null}
          </View>
        </View>

        {Platform.OS !== 'web' ? <ReceiptPdfViewer presentation="overlay" /> : null}
      </View>
    </Modal>
  );
}

type DetailRowProps = {
  label: string;
  value: string;
  labelStyle?: object;
  valueStyle?: object;
};

function DetailRow({ label, value, labelStyle, valueStyle }: DetailRowProps) {
  return (
    <View style={styles.detailRow}>
      <Text style={[styles.detailLabel, labelStyle]}>{label}</Text>
      <Text style={[styles.detailValue, valueStyle]}>{value}</Text>
    </View>
  );
}

function formatCurrency(amount: number) {
  return `Rp ${Math.abs(amount).toLocaleString('id-ID')}`;
}

function getTransactionIconName(transaction: WalletTransaction) {
  if (transaction.status === 'failed') {
    return 'chargingFailure';
  }

  return transaction.type === 'topup' ? 'bankTopup' : 'chargingHistory';
}

function formatSignedCurrency(amount: number) {
  if (amount === 0) {
    return 'Rp 0';
  }

  return `${amount > 0 ? '+' : '-'}${formatCurrency(amount)}`;
}

function formatDetailAmount(amount: number) {
  return formatCurrency(Math.abs(amount));
}

function formatTime(isoDate: string) {
  return formatTransactionDate(isoDate, {
    hour: '2-digit',
    minute: '2-digit'
  });
}

function formatDate(isoDate: string) {
  return formatTransactionDate(isoDate, {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  });
}

function mapTopupToTransaction(topup: TopupApiItem): WalletTransaction {
  const success = topup.status.toLowerCase() === 'paid';

  return {
    id: topup.id,
    amount: topup.amount_idr,
    description: topup.invoice_url ? 'Xendit Invoice' : 'Wallet top-up',
    destination: 'EV-Wallet',
    occurredAt: topup.paid_at ?? topup.created_at,
    orderId: topup.external_id,
    referenceNo: topup.xendit_invoice_id ?? topup.external_id,
    status: success ? 'success' : 'failed',
    title: success ? 'Top Up - Xendit' : `Top Up - ${formatTopupStatus(topup.status)}`,
    type: 'topup',
    paymentMethod: 'Xendit',
    invoiceUrl: topup.invoice_url ?? undefined
  };
}

function formatTopupStatus(status: string) {
  return status
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');
}

function mapSessionToTransaction(session: ChargingSessionApiResponse): WalletTransaction {
  const completed = session.status === 'completed';
  // Charge = a debit (negative). Completed bills actual cost; active holds the deposit.
  const charged = completed ? (session.actual_cost_idr ?? session.deposit_idr) : session.deposit_idr;
  const stationName = session.station_name ?? 'Charging Session';
  const refId = `TXN-${session.id.slice(0, 8).toUpperCase()}`;

  return {
    id: session.id,
    amount: -charged,
    description: completed ? 'Charging settled' : 'Charging in progress',
    connectorType: session.connector_type ?? undefined,
    destination: stationName,
    occurredAt: session.completed_at ?? session.created_at,
    orderId: session.id,
    referenceNo: refId,
    status: 'success',
    title: stationName,
    type: 'charging',
    energyKwh: session.energy_kwh,
    paymentMethod: 'EV-Wallet'
  };
}

function sortTransactions(transactions: WalletTransaction[], sortOrder: TransactionSort) {
  return [...transactions].sort((a, b) => {
    if (sortOrder === 'date_asc') {
      return new Date(a.occurredAt).getTime() - new Date(b.occurredAt).getTime();
    }

    if (sortOrder === 'amount_desc') {
      return Math.abs(b.amount) - Math.abs(a.amount);
    }

    if (sortOrder === 'amount_asc') {
      return Math.abs(a.amount) - Math.abs(b.amount);
    }

    if (sortOrder === 'status') {
      return a.status.localeCompare(b.status) || new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime();
    }

    return new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime();
  });
}

async function copyToClipboard(value: string) {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Fall through to the textarea fallback.
  }

  try {
    if (typeof document === 'undefined') {
      return false;
    }

    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand('copy');
    textarea.remove();
    return copied;
  } catch {
    return false;
  }
}
