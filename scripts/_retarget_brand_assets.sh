#!/bin/bash
set -euo pipefail
FE=/home/ubuntu/alphapilot-repo/frontend
cd "$FE"
cp -f public/logo.png public/brand-logo.png
cp -f public/favicon.png public/brand-favicon.png
files=(
  app/_document.tsx
  app/layout.tsx
  app/page.tsx
  app/login/page.tsx
  app/signup/page.tsx
  components/HeaderBar.tsx
)
for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  sed -i 's|/logo.png|/brand-logo.png|g; s|/favicon.png|/brand-favicon.png|g' "$f"
  echo "patched $f"
done
grep -n 'brand-logo\|brand-favicon\|/logo.png\|/favicon.png' "${files[@]}" || true
# shanghai static mount
cp -f public/brand-logo.png public/brand-favicon.png /home/ubuntu/alphapilot/frontend_out/
echo DONE
