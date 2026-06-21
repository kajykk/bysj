const fs = require('fs');
const path = require('path');

const dir = path.resolve(__dirname, '../public');
if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

const sizes = [192, 512];
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><rect width="512" height="512" fill="#409eff"/><text x="256" y="300" font-size="240" text-anchor="middle" fill="white" font-family="Arial">抑</text></svg>`;

fs.writeFileSync(path.join(dir, 'icon.svg'), svg);

sizes.forEach(s => {
  const outPath = path.join(dir, `icon-${s}x${s}.png`);
  try {
    const { createCanvas } = require('canvas');
    const canvas = createCanvas(s, s);
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#409eff';
    ctx.fillRect(0, 0, s, s);
    ctx.fillStyle = 'white';
    ctx.font = `${Math.floor(s * 0.47)}px Arial`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('抑', s / 2, s / 2 + s * 0.05);
    const buf = canvas.toBuffer('image/png');
    fs.writeFileSync(outPath, buf);
    console.log('Created', outPath);
  } catch (e) {
    console.error('Failed to create icon', s, e.message);
    process.exit(1);
  }
});
