const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '../src/assets/images');
const files = fs.readdirSync(dir).filter(f => f.endsWith('.svg'));

console.log('--- NATIVE ---');
files.forEach(f => {
  const content = fs.readFileSync(path.join(dir, f), 'utf-8');
  console.log(`// ${f}\n${content}`);
});
