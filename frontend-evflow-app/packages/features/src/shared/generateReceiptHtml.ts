import { escapeHtml } from '@evflow/shared';

export type ReceiptData = {
  status: string;
  destination: string;
  time: string;
  date: string;
  transactionId: string;
  orderId: string;
  amount: string;
  total: string;
  typeText: string;
  summaryTitle: string;
  summaryMeta: string;
  energyKwh?: string;
  paymentMethod?: string;
};

export function generateReceiptHtml(data: ReceiptData) {
  const statusClass = data.status.toLowerCase() === 'success' ? 'success' : 'failed';

  return `
    <html>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, user-scalable=no" />
        <style>
          @page { size: A4 portrait; margin: 0; }
          * { box-sizing: border-box; }
          html, body { margin: 0; padding: 0; }
          body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #1f2529; font-size: 12px; }
          #receipt-content { width: 100%; }
          .header { text-align: center; margin-bottom: 18px; }
          .logo { font-size: 24px; font-weight: 800; color: #019495; letter-spacing: 2px; }
          .subtitle { font-size: 12px; color: #6e7a80; margin-top: 4px; }
          .amount { font-size: 28px; font-weight: 800; text-align: center; color: #0f242d; margin-bottom: 4px; }
          .type { font-size: 14px; text-align: center; color: #465359; margin-bottom: 20px; font-weight: 600; }
          .card { background-color: #f6f8f9; border-radius: 10px; padding: 16px; margin-bottom: 14px; break-inside: avoid; page-break-inside: avoid; }
          .summary-title { font-size: 16px; font-weight: 700; margin-bottom: 4px; }
          .summary-meta { font-size: 12px; color: #6e7a80; }
          .section-title { font-size: 11px; font-weight: 800; color: #465359; margin-bottom: 8px; letter-spacing: 1px; }
          .row { display: flex; justify-content: space-between; gap: 16px; padding-top: 10px; padding-bottom: 10px; border-bottom: 1px solid #dee4e6; }
          .row:last-child { border-bottom: none; }
          .label { font-size: 12px; color: #6e7a80; font-weight: 600; }
          .value { font-size: 12px; color: #0f242d; font-weight: 700; text-align: right; overflow-wrap: anywhere; }
          .success { color: #008a4f; }
          .failed { color: #be1a1e; }
          .total-label { font-size: 16px; font-weight: 800; color: #0f242d; }
          .total-value { font-size: 16px; font-weight: 800; color: #019495; text-align: right; }
          .footer { margin-top: 24px; text-align: center; font-size: 10px; color: #9aa4a9; line-height: 1.4; }
        </style>
      </head>
      <body>
        <div id="receipt-content">
          <div class="header">
            <div class="logo">EV-FLOW</div>
            <div class="subtitle">Official Transaction Receipt</div>
          </div>
          
          <div class="amount">${escapeHtml(data.amount)}</div>
          <div class="type">${escapeHtml(data.typeText)}</div>

          <div class="card">
            <div class="summary-title">${escapeHtml(data.summaryTitle)}</div>
            <div class="summary-meta">${escapeHtml(data.summaryMeta)}</div>
          </div>

          <div class="card">
            <div class="section-title">TRANSACTION DETAILS</div>
            
            <div class="row">
              <div class="label">Status</div>
              <div class="value ${statusClass}">${escapeHtml(data.status)}</div>
            </div>
            <div class="row">
              <div class="label">Destination / Origin</div>
              <div class="value">${escapeHtml(data.destination)}</div>
            </div>
            <div class="row">
              <div class="label">Time</div>
              <div class="value">${escapeHtml(data.time)}</div>
            </div>
            <div class="row">
              <div class="label">Date</div>
              <div class="value">${escapeHtml(data.date)}</div>
            </div>
            <div class="row">
              <div class="label">Transaction ID</div>
              <div class="value">${escapeHtml(data.transactionId)}</div>
            </div>
            <div class="row">
              <div class="label">Order ID</div>
              <div class="value">${escapeHtml(data.orderId)}</div>
            </div>
            ${data.energyKwh ? `
            <div class="row">
              <div class="label">Energy</div>
              <div class="value">${escapeHtml(data.energyKwh)}</div>
            </div>` : ''}
            ${data.paymentMethod ? `
            <div class="row">
              <div class="label">Payment Method</div>
              <div class="value">${escapeHtml(data.paymentMethod)}</div>
            </div>` : ''}
          </div>

          <div class="card">
            <div class="row" style="border-bottom: none; padding-bottom: 0;">
              <div class="total-label">Total Amount</div>
              <div class="total-value">${escapeHtml(data.total)}</div>
            </div>
          </div>

          <div class="footer">
            This is a computer generated receipt and does not require a physical signature.<br/>
            Thank you for choosing EV-FLOW.
          </div>
        </div>
      </body>
    </html>
  `;
}
