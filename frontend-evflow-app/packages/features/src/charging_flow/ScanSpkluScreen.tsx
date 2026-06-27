import { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, Pressable } from 'react-native';
import { useNavigate } from 'react-router';
import { Html5Qrcode } from 'html5-qrcode';
import { chargingFlowStyles as styles } from '@evflow/ui';
import { ChargingFlowHeader } from './components/ChargingFlowHeader';

const scannerRegionId = 'spklu-qr-reader';

async function applyScannerTorch(scanner: Html5Qrcode, enabled: boolean) {
  await scanner.applyVideoConstraints({
    advanced: [{ torch: enabled } as MediaTrackConstraintSet]
  } as MediaTrackConstraints);
}

export function ScanSpkluScreen() {
  const navigate = useNavigate();
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [permissionLoading, setPermissionLoading] = useState(true);
  const [hasTorch, setHasTorch] = useState(false);
  const [torchOn, setTorchOn] = useState(false);
  const scannerRef = useRef<Html5Qrcode | null>(null);

  const stopScanner = useCallback(async () => {
    const scanner = scannerRef.current;
    if (!scanner) {
      return;
    }

    try {
      if (scanner.isScanning) {
        await applyScannerTorch(scanner, false);
      }
    } catch (error) {
      console.error('Error disabling torch', error);
    } finally {
      setTorchOn(false);
      setHasTorch(false);
    }

    try {
      if (scanner.isScanning) {
        await scanner.stop();
      }
    } catch (error) {
      console.error('Error stopping scanner', error);
    }

    try {
      scanner.clear();
    } catch (error) {
      console.error('Error clearing scanner', error);
    }

    scannerRef.current = null;
  }, []);

  const toggleTorch = useCallback(() => {
    const scanner = scannerRef.current;
    if (!scanner?.isScanning || !hasTorch) {
      return;
    }

    const nextTorchState = !torchOn;
    applyScannerTorch(scanner, nextTorchState)
      .then(() => setTorchOn(nextTorchState))
      .catch(error => {
        console.error('Error toggling torch', error);
        setTorchOn(false);
      });
  }, [hasTorch, torchOn]);

  const stopAndNavigate = useCallback((path: string) => {
    stopScanner().finally(() => navigate(path));
  }, [navigate, stopScanner]);

  const checkCameraPermission = useCallback(() => {
    setPermissionLoading(true);
    setPermissionError(null);
    
    Html5Qrcode.getCameras().then(devices => {
      if (devices && devices.length) {
        setHasPermission(true);
      } else {
        setHasPermission(false);
      }
    }).catch(err => {
      setPermissionError(err instanceof Error ? err.message : 'Camera permission denied or camera not found.');
      setHasPermission(false);
    }).finally(() => {
      setPermissionLoading(false);
    });
  }, []);

  useEffect(() => {
    let mounted = true;

    const detectPersistedPermission = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        if (mounted) {
          setPermissionError('Camera is not available in this web browser.');
          setHasPermission(false);
          setPermissionLoading(false);
        }
        return;
      }

      try {
        const permissionStatus = await navigator.permissions?.query({ name: 'camera' as PermissionName });
        if (!mounted) return;

        setHasPermission(permissionStatus?.state !== 'denied');
        setPermissionLoading(false);

        if (permissionStatus) {
          permissionStatus.onchange = () => {
            setHasPermission(permissionStatus.state !== 'denied');
          };
        }
      } catch {
        if (mounted) {
          setHasPermission(true);
          setPermissionLoading(false);
        }
      }
    };

    detectPersistedPermission();

    return () => {
      mounted = false;
      stopScanner();
    };
  }, [stopScanner]);

  useEffect(() => {
    if (hasPermission) {
      const html5QrCode = new Html5Qrcode(scannerRegionId);
      scannerRef.current = html5QrCode;
      
      html5QrCode.start(
        { facingMode: "environment" },
        {
          fps: 10,
          qrbox: { width: 250, height: 250 }
        },
        (decodedText, decodedResult) => {
          stopAndNavigate('/charging-flow/initialize');
        },
        (errorMessage) => {
          // ignore scan errors (they happen every frame that no code is detected)
        }
      ).catch(err => {
        console.error("Error starting scanner", err);
        setPermissionError(err instanceof Error ? err.message : 'Camera permission denied or camera not found.');
        setHasPermission(false);
        setHasTorch(false);
        setTorchOn(false);
      }).then(() => {
        if (!html5QrCode.isScanning) {
          return;
        }

        try {
          const capabilities = html5QrCode.getRunningTrackCapabilities() as MediaTrackCapabilities & { torch?: boolean };
          setHasTorch(Boolean(capabilities.torch));
        } catch (error) {
          console.error('Error reading torch capability', error);
          setHasTorch(false);
        }
      });

      return () => {
        stopScanner();
      };
    }
  }, [hasPermission, stopAndNavigate, stopScanner]);

  return (
    <View style={styles.page}>
      <style>{`
        #${scannerRegionId} {
          display: flex;
          justify-content: center;
          align-items: center;
          background-color: #000;
        }
        #${scannerRegionId} video {
          object-fit: cover !important;
          width: 100% !important;
          height: 100% !important;
        }
        #${scannerRegionId} canvas {
          display: none !important;
        }
      `}</style>
      <ChargingFlowHeader
        title="Scan SPKLU QR Code"
        onBack={() => stopAndNavigate('/ev-driver/map')}
        rightIconName={hasTorch ? 'flashlight' : undefined}
        rightIconColor={torchOn ? '#01aeb8' : '#191C1D'}
        rightIconSize={22}
        onRightPress={hasTorch ? toggleTorch : undefined}
      />

      <View style={styles.cameraContainer}>
        {hasPermission !== true && !permissionLoading ? (
          <View style={styles.permissionPrompt}>
            <Text style={styles.permissionPromptText}>
              Camera access is required to scan the SPKLU QR code in this web browser.
            </Text>
            {permissionError ? <Text style={styles.permissionPromptSubtext}>{permissionError}</Text> : null}
            <Pressable accessibilityRole="button" onPress={checkCameraPermission} style={styles.secondaryPermissionButton}>
              <Text style={styles.secondaryPermissionButtonText}>
                {permissionLoading ? 'Checking Camera...' : 'Allow Browser Camera Access'}
              </Text>
            </Pressable>
          </View>
        ) : hasPermission === true ? (
          <>
            <View style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
              <div id={scannerRegionId} style={{ width: '100%', height: '100%' }} />
              <View style={[styles.cameraOverlay, { backgroundColor: 'transparent', pointerEvents: 'box-none' } as any]}>
                <View style={[styles.cameraCutout, { boxShadow: '0 0 0 9999px rgba(0,0,0,0.5)' } as any]} />
                <View style={styles.cameraTextContainer}>
                  <Text style={styles.cameraInstructions}>
                    Position the QR code or barcode found on the SPKLU connector inside the frame to initialize payment.
                  </Text>
                  <Text style={styles.manualEntryLink} onPress={() => {
                    stopAndNavigate('/charging-flow/initialize');
                  }}>
                    Can't scan? Enter Station ID manually
                  </Text>
                </View>
              </View>
            </View>
            
            <View style={styles.cameraNoticeCard}>
              <Text style={{ fontSize: 24, color: '#01e0f0' }}>ⓘ</Text>
              <Text style={styles.cameraNoticeText}>Make sure you have selected the correct plug profile on the previous screen.</Text>
            </View>
          </>
        ) : (
          <View style={styles.camera} />
        )}
      </View>
    </View>
  );
}
