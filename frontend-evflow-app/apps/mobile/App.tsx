import { StatusBar } from 'expo-status-bar';
import { SpaceGrotesk_400Regular, SpaceGrotesk_500Medium, SpaceGrotesk_600SemiBold, SpaceGrotesk_700Bold, useFonts } from '@expo-google-fonts/space-grotesk';
import { cloneElement } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AppRouter } from '@evflow/features';

installDefaultFont(Text);
installDefaultFont(TextInput);

export default function App() {
  const [fontsLoaded] = useFonts({
    SpaceGrotesk_400Regular,
    SpaceGrotesk_500Medium,
    SpaceGrotesk_600SemiBold,
    SpaceGrotesk_700Bold
  });

  if (!fontsLoaded) {
    return null;
  }

  return (
    <SafeAreaProvider>
      <View style={{ flex: 1 }}>
        <AppRouter />
        <StatusBar style="auto" />
      </View>
    </SafeAreaProvider>
  );
}

function installDefaultFont(Component: any) {
  if (Component.__evflowSpaceGroteskInstalled || !Component.render) {
    return;
  }

  const originalRender = Component.render;
  Component.render = function renderWithSpaceGrotesk(...args: unknown[]) {
    const element = originalRender.apply(this, args);
    const flattenedStyle = StyleSheet.flatten(element.props?.style) ?? {};
    const fontFamily = getSpaceGroteskFamily(flattenedStyle.fontWeight);
    const { fontWeight: _fontWeight, ...styleWithoutWeight } = flattenedStyle;

    return cloneElement(element, {
      style: [styleWithoutWeight, { fontFamily }]
    });
  };
  Component.__evflowSpaceGroteskInstalled = true;
}

function getSpaceGroteskFamily(fontWeight: unknown) {
  const weight = typeof fontWeight === 'string' ? Number(fontWeight) : fontWeight;

  if (weight === 'bold' || weight === 700 || weight === 800 || weight === 900) {
    return 'SpaceGrotesk_700Bold';
  }

  if (weight === 600) {
    return 'SpaceGrotesk_600SemiBold';
  }

  if (weight === 500) {
    return 'SpaceGrotesk_500Medium';
  }

  return 'SpaceGrotesk_400Regular';
}
