import { Alert } from 'react-native';
// @ts-ignore
import html2pdf from 'html2pdf.js';
import { generateReceiptHtml, type ReceiptData } from './generateReceiptHtml';

export type { ReceiptData };

const PAGE_MARGIN_CM = 1.3;

export async function downloadReceipt(data?: ReceiptData) {
  if (!data) {
    Alert.alert('Download Receipt', 'Receipt data unavailable.');
    return;
  }

  const html = generateReceiptHtml(data);
  const pdfWindow = window.open('', '_blank');

  try {
    const element = document.createElement('div');
    element.innerHTML = html;
    const options: any = {
      margin: PAGE_MARGIN_CM,
      filename: `receipt_${data.transactionId}.pdf`,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2 },
      pagebreak: { mode: ['avoid-all'] },
      jsPDF: { unit: 'cm', format: 'a4', orientation: 'portrait' }
    };
    
    const pdfUrl = await html2pdf().set(options).from(element).output('bloburl');

    if (pdfWindow) {
      pdfWindow.document.title = `Receipt ${data.transactionId}`;
      pdfWindow.document.body.style.margin = '0';
      pdfWindow.document.body.innerHTML = `
        <iframe
          src="${pdfUrl}"
          title="Receipt PDF"
          style="border: 0; width: 100vw; height: 100vh;"
        ></iframe>
      `;
      pdfWindow.focus();
    } else {
      window.open(pdfUrl, '_blank');
    }

  } catch (error) {
    console.error('Failed to generate receipt PDF', error);
    pdfWindow?.close();
    Alert.alert('Error', 'Unable to generate receipt PDF.');
  }
}
