import os
from PIL import Image, ImageDraw, ImageFont

dir = r'e:/code/bysj/frontend/public'
os.makedirs(dir, exist_ok=True)

sizes = [192, 512]
for s in sizes:
    img = Image.new('RGB', (s, s), '#409eff')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('arial.ttf', int(s*0.47))
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0,0), '抑', font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    draw.text(((s-tw)/2, (s-th)/2 - s*0.02), '抑', fill='white', font=font)
    img.save(os.path.join(dir, f'icon-{s}x{s}.png'))
    print('Created', s)

svg = '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><rect width="512" height="512" fill="#409eff"/><text x="256" y="300" font-size="240" text-anchor="middle" fill="white" font-family="Arial">抑</text></svg>'
with open(os.path.join(dir, 'icon.svg'), 'w', encoding='utf-8') as f:
    f.write(svg)
print('Done')
