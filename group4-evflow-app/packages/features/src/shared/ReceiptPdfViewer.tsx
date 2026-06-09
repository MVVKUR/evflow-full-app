import { useEffect, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { WebView } from 'react-native-webview';
import { useAppSafeAreaInsets } from './useAppSafeAreaInsets';

type ReceiptPdfViewerState = {
  title: string;
  uri: string;
};

type ReceiptPdfViewerProps = {
  presentation?: 'modal' | 'overlay';
};

const viewerHandlers: Array<(state: ReceiptPdfViewerState) => void> = [];

export function openReceiptPdf(uri: string, title = 'Receipt') {
  viewerHandlers[viewerHandlers.length - 1]?.({ title, uri });
}

export function ReceiptPdfViewer({ presentation = 'modal' }: ReceiptPdfViewerProps) {
  const [viewerState, setViewerState] = useState<ReceiptPdfViewerState | null>(null);
  const insets = useAppSafeAreaInsets();

  useEffect(() => {
    viewerHandlers.push(setViewerState);

    return () => {
      const handlerIndex = viewerHandlers.lastIndexOf(setViewerState);
      if (handlerIndex >= 0) {
        viewerHandlers.splice(handlerIndex, 1);
      }
    };
  }, []);

  const content = (
    <View style={[styles.container, presentation === 'overlay' && styles.overlayContainer]}>
      <View style={[styles.header, { paddingTop: insets.top }]}>
        <Pressable accessibilityLabel="Close receipt PDF" accessibilityRole="button" onPress={() => setViewerState(null)} style={styles.headerButton}>
          <Text style={styles.closeText}>Close</Text>
        </Pressable>
        <Text numberOfLines={1} style={styles.title}>{viewerState?.title ?? 'Receipt'}</Text>
        <View style={styles.headerButton} />
      </View>

      {viewerState ? (
        <WebView
          allowFileAccess
          allowFileAccessFromFileURLs
          allowingReadAccessToURL={viewerState.uri}
          originWhitelist={['*']}
          renderLoading={() => (
            <View style={styles.loading}>
              <ActivityIndicator color="#019495" />
            </View>
          )}
          source={{ uri: viewerState.uri }}
          startInLoadingState
          style={[styles.webView, { marginBottom: insets.bottom }]}
        />
      ) : null}
    </View>
  );

  if (presentation === 'overlay') {
    return viewerState ? content : null;
  }

  return (
    <Modal animationType="slide" visible={Boolean(viewerState)} onRequestClose={() => setViewerState(null)}>
      {content}
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#ffffff',
    flex: 1
  },
  overlayContainer: {
    bottom: 0,
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
    zIndex: 10
  },
  header: {
    alignItems: 'center',
    borderBottomColor: '#eef1f4',
    borderBottomWidth: 1,
    flexDirection: 'row',
    minHeight: 56,
    paddingHorizontal: 12
  },
  headerButton: {
    alignItems: 'center',
    height: 44,
    justifyContent: 'center',
    width: 72
  },
  closeText: {
    color: '#005f64',
    fontSize: 15,
    fontWeight: '700'
  },
  title: {
    color: '#1f2529',
    flex: 1,
    fontSize: 16,
    fontWeight: '800',
    textAlign: 'center'
  },
  webView: {
    flex: 1
  },
  loading: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    bottom: 0,
    justifyContent: 'center',
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0
  }
});
