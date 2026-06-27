import { Alert } from 'react-native';
// @ts-ignore
import html2pdf from 'html2pdf.js';
import { generateReceiptHtml, type ReceiptData } from './generateReceiptHtml';

export type { ReceiptData };

const PAGE_MARGIN_CM = 1.3;

export async function downloadReceipt(data?: ReceiptData) {
  if (!data) {
    Alert.alert('Download Receipt', 'Receipt data unavailable.');
    return false;
  }

  const html = generateReceiptHtml(data);

  try {
    const element = document.createElement('div');
    element.innerHTML = html;
    const options: any = {
      margin: PAGE_MARGIN_CM,
      filename: `EVFLOW-Invoice-${data.transactionId}.pdf`,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2 },
      pagebreak: { mode: ['avoid-all'] },
      jsPDF: { unit: 'cm', format: 'a4', orientation: 'portrait' }
    };
    
    const blob = await html2pdf().set(options).from(element).output('blob');
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = options.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    return true;
  } catch (error) {
    Alert.alert('Error', 'Unable to generate receipt PDF.');
    return false;
  }
}
