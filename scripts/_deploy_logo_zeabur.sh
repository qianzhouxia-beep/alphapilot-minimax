#!/bin/bash
# Replace logo assets, sync score UI page, commit & push for Zeabur redeploy.
set -euo pipefail

REPO=/home/ubuntu/alphapilot-repo
FE=$REPO/frontend
LOGO_SRC=${1:-/tmp/AlphaPilot_logo_new.png}
export NVM_DIR="$HOME/.nvm"
# shellcheck disable=SC1090
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm use 20 >/dev/null 2>&1 || true

echo "=== logo source ==="
ls -la "$LOGO_SRC"

python3 - <<'PY' "$LOGO_SRC" "$FE"
import sys
from pathlib import Path
try:
    from PIL import Image
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "pillow", "-q"])
    from PIL import Image

src = Path(sys.argv[1])
fe = Path(sys.argv[2])
img = Image.open(src).convert("RGBA")
# knock out near-black background so logo sits cleanly on dark UI
pixels = img.load()
w, h = img.size
for y in range(h):
    for x in range(w):
        r, g, b, a = pixels[x, y]
        if r < 28 and g < 28 and b < 28:
            pixels[x, y] = (r, g, b, 0)

# trim transparent borders
bbox = img.getbbox()
if bbox:
    img = img.crop(bbox)

public = fe / "public"
public.mkdir(exist_ok=True)
logo_path = public / "logo.png"
img.save(logo_path, "PNG", optimize=True)
print("wrote", logo_path, img.size)

# favicon: icon-only crop (left portion ~ square of mark)
iw, ih = img.size
# mark is roughly left ~ih width of the wordmark
mark = img.crop((0, 0, min(ih + 8, iw), ih))
mark_sq = Image.new("RGBA", (max(mark.size), max(mark.size)), (0, 0, 0, 0))
ox = (mark_sq.size[0] - mark.size[0]) // 2
oy = (mark_sq.size[1] - mark.size[1]) // 2
mark_sq.paste(mark, (ox, oy), mark)
fav = mark_sq.resize((64, 64), Image.Resampling.LANCZOS)
fav_path = public / "favicon.png"
fav.save(fav_path, "PNG", optimize=True)
print("wrote", fav_path)

# og image: logo centered on dark canvas
og = Image.new("RGBA", (1200, 630), (8, 14, 24, 255))
scale = min(900 / img.size[0], 220 / img.size[1])
nw, nh = int(img.size[0] * scale), int(img.size[1] * scale)
resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
og.paste(resized, ((1200 - nw) // 2, (630 - nh) // 2), resized)
og_path = public / "og.png"
og.convert("RGB").save(og_path, "PNG", optimize=True)
print("wrote", og_path)
PY

# sync score UI page already on shanghai
if [ -f /home/ubuntu/alphapilot/frontend_cn_page.tsx ]; then
  cp -f /home/ubuntu/alphapilot/frontend_cn_page.tsx "$FE/app/cn/page.tsx"
  echo "synced app/cn/page.tsx"
fi
if [ -f /home/ubuntu/alphapilot/HeaderBar.tsx ]; then
  mkdir -p "$FE/components"
  cp -f /home/ubuntu/alphapilot/HeaderBar.tsx "$FE/components/HeaderBar.tsx"
  echo "synced HeaderBar.tsx"
fi

# also refresh local static out for shanghai API mount
cd "$FE"
npm run build
rsync -a --delete out/ /home/ubuntu/alphapilot/frontend_out/
echo "synced shanghai frontend_out"

# git commit + push (Zeabur watches GitHub)
cd "$REPO"
git status -sb
git add frontend/public/logo.png frontend/public/favicon.png frontend/public/og.png frontend/app/cn/page.tsx
git add -u frontend/components/HeaderBar.tsx 2>/dev/null || true
if git diff --cached --quiet; then
  echo "nothing to commit"
else
  git commit -m "$(cat <<'EOF'
update brand logo and CN score display for Zeabur

Replace site logo/favicon/og with the new AlphaPilot mark, and ship the
VM2.5 confidence-score UI so production no longer shows exam-style percents.
EOF
)"
fi

echo "=== push ==="
if git push origin HEAD; then
  echo "PUSH_OK"
else
  echo "PUSH_FAILED — check credentials"
  exit 2
fi

echo DONE
