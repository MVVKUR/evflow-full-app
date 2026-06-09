import React from 'react';
import ReactDOM from 'react-dom/client';
import { Text, TextInput } from 'react-native';
import { AppRouter } from '@evflow/features';
import './styles.css';

installDefaultFont(Text);
installDefaultFont(TextInput);

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <AppRouter />
  </React.StrictMode>
);

function installDefaultFont(Component: any) {
  if (Component.__evflowSpaceGroteskInstalled) {
    return;
  }

  Component.defaultProps = {
    ...Component.defaultProps,
    style: [{ fontFamily: 'Space Grotesk' }, Component.defaultProps?.style]
  };
  Component.__evflowSpaceGroteskInstalled = true;
}
