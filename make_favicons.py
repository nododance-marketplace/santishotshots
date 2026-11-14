#!/usr/bin/env python3
"""
make_favicons.py — builds assets/logo.png and the full favicon set from
'Hotshots Logo.jpg' (circular "Santi's Hot Shots" badge).

- Detects the badge in the photo (saturation mask -> bounding box), crops it
  and masks it to a clean circle with transparent corners -> assets/logo.png.
- Big sizes (96/192/512/apple-touch) keep the full badge detail.
- Small sizes (16/32/.ico) use a hand-drawn STYLIZED mini-badge (navy circle,
  gold rings, SANTI'S + HOT SHOTS bands) instead of a blind downscale — the
  real artwork turns to mush below ~48px, this stays legible at 16px.

Run again any time the source logo changes:  python make_favicons.py
"""
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
import math
import os

SRC = "Hotshots Logo.jpg"
OUT = "assets"
NAVY = (27, 42, 74)          # #1B2A4A
NAVY2 = (20, 32, 58)
GOLD = (201, 162, 39)        # #C9A227
GOLD2 = (227, 179, 60)
FLAME = (232, 99, 26)        # #E8631A
RED = (217, 79, 43)          # #D94F2B
WHITE = (244, 241, 232)
BIG = 1024                   # working resolution for the circle master


def badge_circle():
    """Find the circular badge in the photo and return it at BIGxBIG RGBA,
    background removed, everything outside the circle transparent."""
    img = Image.open(SRC).convert("RGBA")
    hsv = img.convert("HSV")
    sat = hsv.split()[1]
    # grey concrete background is nearly neutral; the badge art is not
    mask = sat.point(lambda v: 255 if v > 60 else 0)
    bbox = mask.getbbox()
    if not bbox:
        raise SystemExit("could not locate the badge (no saturated pixels)")
    cx = (bbox[0] + bbox[2]) // 2
    cy = (bbox[1] + bbox[3]) // 2
    side = max(bbox[2] - bbox[0], bbox[3] - bbox[1])
    half = side * 0.52                      # tiny margin, trims sticker edge
    badge = img.crop((int(cx - half), int(cy - half),
                      int(cx + half), int(cy + half)))
    badge = badge.resize((BIG, BIG), Image.LANCZOS)

    ring = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(ring).ellipse((3, 3, BIG - 3, BIG - 3), fill=255)
    ring = ring.filter(ImageFilter.GaussianBlur(1.5))

    out = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    out.paste(badge, (0, 0), ring)
    return out


def stylized_badge(size=512):
    """Flat vector-style mini version of the badge for tiny favicon sizes."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = size / 512.0
    d.ellipse((10 * s, 10 * s, 502 * s, 502 * s), fill=GOLD)
    d.ellipse((28 * s, 28 * s, 484 * s, 484 * s), fill=NAVY)
    d.ellipse((40 * s, 40 * s, 472 * s, 472 * s),
              outline=WHITE + (230,), width=max(2, int(5 * s)))
    # top banner — SANTI'S
    d.rounded_rectangle((66 * s, 108 * s, 446 * s, 224 * s), radius=int(24 * s),
                        fill=GOLD2, outline=NAVY2 + (255,), width=max(2, int(6 * s)))
    f1 = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", int(96 * s))
    d.text((256 * s, 164 * s), "SANTI'S", font=f1, fill=NAVY2 + (255,), anchor="mm")
    # bottom banner — HOT SHOTS
    d.rounded_rectangle((84 * s, 296 * s, 428 * s, 396 * s), radius=int(24 * s),
                        fill=RED, outline=NAVY2 + (255,), width=max(2, int(6 * s)))
    f2 = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", int(64 * s))
    d.text((256 * s, 344 * s), "HOT SHOTS", font=f2, fill=WHITE + (255,), anchor="mm")
    # center star
    cx, cy, R = 256 * s, 262 * s, 40 * s
    pts = [(cx + R * math.sin(i * math.pi / 5), cy - R * math.cos(i * math.pi / 5))
           for i in range(10)]
    d.polygon(pts[0::2], fill=GOLD)
    return im


def main():
    os.makedirs(OUT, exist_ok=True)
    circle = badge_circle()

    # header logo (real artwork, transparent circle)
    circle.resize((512, 512), Image.LANCZOS).save(f"{OUT}/logo.png")

    # large favicons — full badge detail
    for size, name in [(96, "favicon-96x96.png"),
                       (192, "android-chrome-192x192.png"),
                       (512, "android-chrome-512x512.png")]:
        circle.resize((size, size), Image.LANCZOS).save(f"{OUT}/{name}")

    # small favicons — stylized mini-badge (legible at 16px)
    mini = stylized_badge(512)
    for size, name in [(16, "favicon-16x16.png"), (32, "favicon-32x32.png")]:
        mini.resize((size, size), Image.LANCZOS).save(f"{OUT}/{name}")
    mini.resize((48, 48), Image.LANCZOS).save(
        f"{OUT}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    # apple touch icon: square, no alpha, real badge on navy
    sq = Image.new("RGBA", (BIG, BIG), NAVY + (255,))
    sq.paste(circle, (0, 0), circle.split()[3])
    sq.convert("RGB").resize((180, 180), Image.LANCZOS).save(
        f"{OUT}/apple-touch-icon.png")

    # preview sheet so a human can judge the small sizes (magnified)
    sheet = Image.new("RGBA", (3 * 138 + 28, 158), NAVY + (255,))
    x = 14
    for size, zoom in [(16, 8), (32, 4), (48, 2)]:
        p = mini.resize((size, size), Image.LANCZOS)
        sheet.alpha_composite(p.resize((size * zoom, size * zoom), Image.NEAREST), (x, 10))
        x += size * zoom + 14
    sheet.save(f"{OUT}/_preview.png")
    print("wrote", OUT, "->", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
