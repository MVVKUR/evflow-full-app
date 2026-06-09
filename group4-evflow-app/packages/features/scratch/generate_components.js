const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '../src/assets/images');
const svgFiles = [
  'connector.svg', 'timer.svg', 'wallet-with-bg.svg', 'piggy-bank.svg', 
  'receipt.svg', 'location-info.svg', 'shield.svg', 'lightning-icon.svg',
  'copy-button.svg', 'download.svg', 'wallet.svg'
];

let nativeCode = `import Svg, { Path } from 'react-native-svg';\n\n`;
nativeCode += `export type ChargingIconName = 'connector' | 'timer' | 'wallet_bg' | 'piggy' | 'receipt' | 'location' | 'shield' | 'lightning' | 'copy' | 'download' | 'wallet';\n\n`;
nativeCode += `export function ChargingFlowIcon({ name, color, size = 24 }: { name: ChargingIconName, color?: string, size?: number }) {\n`;

let webCode = `import { createElement, useMemo } from 'react';\n\n`;
webCode += `export type ChargingIconName = 'connector' | 'timer' | 'wallet_bg' | 'piggy' | 'receipt' | 'location' | 'shield' | 'lightning' | 'copy' | 'download' | 'wallet';\n\n`;

const mapping = {
  'connector.svg': 'connector',
  'timer.svg': 'timer',
  'wallet-with-bg.svg': 'wallet_bg',
  'piggy-bank.svg': 'piggy',
  'receipt.svg': 'receipt',
  'location-info.svg': 'location',
  'shield.svg': 'shield',
  'lightning-icon.svg': 'lightning',
  'copy-button.svg': 'copy',
  'download.svg': 'download',
  'wallet.svg': 'wallet'
};

svgFiles.forEach(f => {
  const content = fs.readFileSync(path.join(dir, f), 'utf-8');
  const dMatch = content.match(/d="([^"]+)"/);
  const vbMatch = content.match(/viewBox="([^"]+)"/);
  const fillMatch = content.match(/fill="([^"]+)"/);
  
  if (dMatch && vbMatch) {
    const key = mapping[f];
    const fill = fillMatch ? fillMatch[1] : '#000';
    
    nativeCode += `  if (name === '${key}') {\n`;
    nativeCode += `    return (\n`;
    nativeCode += `      <Svg width={size} height={size} viewBox="${vbMatch[1]}" fill="none">\n`;
    nativeCode += `        <Path d="${dMatch[1]}" fill={color || "${fill}"} />\n`;
    nativeCode += `      </Svg>\n`;
    nativeCode += `    );\n  }\n\n`;
    
    webCode += `import ${key}Icon from '../../assets/images/${f}?raw';\n`;
  }
});

nativeCode += `  return null;\n}\n`;

webCode += `\nconst icons: Record<ChargingIconName, string> = {\n`;
svgFiles.forEach(f => {
  webCode += `  ${mapping[f]}: ${mapping[f]}Icon,\n`;
});
webCode += `};\n\n`;

webCode += `export function ChargingFlowIcon({ name, color, size = 24 }: { name: ChargingIconName, color?: string, size?: number }) {\n`;
webCode += `  const svg = useMemo(() => {\n`;
webCode += `    let raw = icons[name];\n`;
webCode += `    if (color) {\n`;
webCode += `      raw = raw.replace(/fill="[^"]+"/g, \`fill="\${color}"\`);\n`;
webCode += `    }\n`;
webCode += `    return raw.replace('<svg ', \`<svg width="\${size}" height="\${size}" style="display:block" \`);\n`;
webCode += `  }, [color, name, size]);\n\n`;
webCode += `  return createElement('span', {\n`;
webCode += `    dangerouslySetInnerHTML: { __html: svg },\n`;
webCode += `    style: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }\n`;
webCode += `  });\n}\n`;

fs.writeFileSync(path.join(__dirname, '../src/charging_flow/components/ChargingFlowIcon.native.tsx'), nativeCode);
fs.writeFileSync(path.join(__dirname, '../src/charging_flow/components/ChargingFlowIcon.tsx'), webCode);
console.log('Icons updated successfully');
