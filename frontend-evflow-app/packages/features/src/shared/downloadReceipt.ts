import { Alert } from 'react-native';
import * as Print from 'expo-print';
import { generateReceiptHtml, type ReceiptData } from './generateReceiptHtml';
import { openReceiptPdf } from './ReceiptPdfViewer';

export type { ReceiptData };

const A4_WIDTH_POINTS = 595;
const A4_HEIGHT_POINTS = 842;
const PAGE_MARGIN_POINTS = 36.85;

export async function downloadReceipt(data?: ReceiptData) {
  if (!data) {
    Alert.alert('Download Receipt', 'Receipt data unavailable.');
    return;
  }

  const html = generateReceiptHtml(data);

  try {
    const { uri } = await Print.printToFileAsync({
      height: A4_HEIGHT_POINTS,
      html,
      margins: {
        bottom: PAGE_MARGIN_POINTS,
        left: PAGE_MARGIN_POINTS,
        right: PAGE_MARGIN_POINTS,
        top: PAGE_MARGIN_POINTS
      },
      width: A4_WIDTH_POINTS
    });

    openReceiptPdf(uri, `Receipt ${data.transactionId}`);
  } catch (error) {
    console.error('Failed to generate receipt PDF', error);
    Alert.alert('Error', 'Unable to generate receipt PDF.');
  }
}
