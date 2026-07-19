#!/usr/bin/env python3
"""Process AlphaPilot logo for light UI: knock out black bg, emit logo/favicon/og."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow", "-q"])
    from PIL import Image

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])  # frontend/public


def knock_black(img: Image.Image) -> Image.Image:
    """Stronger knockout for opaque black / near-black backgrounds (incl. slight noise)."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            mx = max(r, g, b)
            # Solid near-black, or dark with slight channel noise
            if (r < 40 and g < 40 and b < 40) or (r + g + b < 90 and mx < 50):
                px[x, y] = (r, g, b, 0)
            elif mx < 55 and r + g + b < 120 and abs(r - g) < 18 and abs(g - b) < 18 and abs(r - b) < 18:
                # near-black with slight noise (desaturated dark)
                px[x, y] = (r, g, b, 0)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img = knock_black(Image.open(SRC))
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    logo_path = OUT / "logo.png"
    img.save(logo_path, "PNG", optimize=True)
    print("logo", logo_path, img.size)

    # favicon: left mark (~ square)
    iw, ih = img.size
    mark_w = min(max(ih + 12, int(iw * 0.28)), iw)
    mark = img.crop((0, 0, mark_w, ih))
    side = max(mark.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(mark, ((side - mark.size[0]) // 2, (side - mark.size[1]) // 2), mark)
    fav = sq.resize((64, 64), Image.Resampling.LANCZOS)
    fav_path = OUT / "favicon.png"
    fav.save(fav_path, "PNG", optimize=True)
    print("favicon", fav_path)

    # light og canvas (#F5F5F7)
    og = Image.new("RGBA", (1200, 630), (245, 245, 247, 255))
    scale = min(900 / img.size[0], 220 / img.size[1])
    nw, nh = int(img.size[0] * scale), int(img.size[1] * scale)
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    og.paste(resized, ((1200 - nw) // 2, (630 - nh) // 2), resized)
    og_path = OUT / "og.png"
    og.convert("RGB").save(og_path, "PNG", optimize=True)
    print("og", og_path)
    print("OK")


if __name__ == "__main__":
    main()
