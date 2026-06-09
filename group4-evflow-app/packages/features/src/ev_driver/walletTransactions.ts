export type WalletTransactionStatus = 'success' | 'failed';
export type WalletTransactionType = 'charging' | 'topup';

export type WalletTransaction = {
  id: string;
  title: string;
  description: string;
  occurredAt: string;
  connectorType?: string;
  amount: number;
  type: WalletTransactionType;
  status: WalletTransactionStatus;
  referenceNo: string;
  orderId: string;
  destination: string;
  invoiceUrl?: string;
};

export const walletTransactions: WalletTransaction[] = [
  {
    id: 'txn-2026-8849x',
    title: 'SPKLU PLN Sukses - Thamrin',
    description: '31 May 2026, 01:52 WIB',
    occurredAt: '2026-05-31T01:52:00+07:00',
    connectorType: 'CCS Type 2',
    amount: -51820,
    type: 'charging',
    status: 'success',
    referenceNo: 'TXN-2026-8849X',
    orderId: 'Xendit_26053101528849',
    destination: 'EV - Wallet'
  },
  {
    id: 'txn-2026-7812b',
    title: 'Gading Serpong Supercharger',
    description: '30 May 2026, 18:15 WIB',
    occurredAt: '2026-05-30T18:15:00+07:00',
    connectorType: 'AC Type 2',
    amount: -32400,
    type: 'charging',
    status: 'success',
    referenceNo: 'TXN-2026-7812B',
    orderId: 'Xendit_26053018157812',
    destination: 'EV - Wallet'
  },
  {
    id: 'txn-2026-8849-topup',
    title: 'Top Up - BCA Virtual Account',
    description: '29 May 2026, 10:05 WIB',
    occurredAt: '2026-05-29T10:05:00+07:00',
    amount: 150000,
    type: 'topup',
    status: 'success',
    referenceNo: 'TXN-2026-8849X',
    orderId: 'Xendit_26060592036383523773',
    destination: 'EV - Wallet'
  },
  {
    id: 'txn-2026-6402s',
    title: 'Senayan City Mall Station',
    description: '28 May 2026, 14:20 WIB',
    occurredAt: '2026-05-28T14:20:00+07:00',
    connectorType: 'CCS Type 2',
    amount: -78210,
    type: 'charging',
    status: 'success',
    referenceNo: 'TXN-2026-6402S',
    orderId: 'Xendit_26052814206402',
    destination: 'EV - Wallet'
  },
  {
    id: 'txn-2026-5700f',
    title: 'Jakarta-Cikampek KM 57',
    description: '27 May 2026, 22:45 WIB',
    occurredAt: '2026-05-27T22:45:00+07:00',
    connectorType: 'Hyper Fast',
    amount: 0,
    type: 'charging',
    status: 'failed',
    referenceNo: 'TXN-2026-5700F',
    orderId: 'Xendit_26052722455700',
    destination: 'EV - Wallet'
  }
];
