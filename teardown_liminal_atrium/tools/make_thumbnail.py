#!/usr/bin/env python3
"""Mod thumbnail: the exterior render with the title over it -> preview.jpg (1280 x 720, < 1 MB for the Workshop).

    python3 tools/make_thumbnail.py [previews/workshop/01_exterior.jpg]"""
import os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "previews", "workshop", "01_exterior.jpg")
im = Image.open(src).convert("RGB").resize((1280, 720), Image.LANCZOS)
# soft dark band at the bottom so the title reads
band = Image.new("L", im.size, 0)
ImageDraw.Draw(band).rectangle([0, 540, 1280, 720], fill=170)
band = band.filter(ImageFilter.GaussianBlur(60))
im = Image.composite(Image.new("RGB", im.size, (12, 8, 24)), im, band)
d = ImageDraw.Draw(im)
title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 64)
sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 21)
glow = Image.new("RGBA", im.size, (0, 0, 0, 0))
ImageDraw.Draw(glow).text((52, 578), "LIMINAL ATRIUM", font=title, fill=(200, 160, 255, 200))
glow = glow.filter(ImageFilter.GaussianBlur(10))
im.paste(glow, (0, 0), glow)
d.text((52, 578), "LIMINAL ATRIUM", font=title, fill=(246, 238, 255))
d.text((56, 660), "a hotel at night  ·  6 floors  ·  basement mall  ·  rooftop glasshouse  ·  helipad  ·  sandbox",
       font=sub, fill=(214, 204, 236))
out = os.path.join(ROOT, "preview.jpg")
im.save(out, quality=90)
print("saved", out, os.path.getsize(out) // 1024, "KB")
