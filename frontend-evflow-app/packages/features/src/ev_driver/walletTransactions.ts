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
  energyKwh?: number;
  paymentMethod?: string;
};
