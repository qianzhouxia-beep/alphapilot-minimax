#!/usr/bin/env python3
"""Apply visual optimization changes to AlphaPilot frontend files."""

import os

BASE = r"D:\AI\alphapilot\部署文件\frontend"

# === 1) HeaderBar.tsx changes ===
hb_path = os.path.join(BASE, "components", "HeaderBar.tsx")
with open(hb_path, "r", encoding="utf-8-sig") as f:
    hb = f.read()

# 1a) Replace star emoji with SVG star
old_star = '<span style={{ fontSize: 14 }}>\u2b50</span>'
new_star = '<svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>'
count = hb.count(old_star)
assert count == 1, f"Expected exactly 1 star emoji occurrence, found {count}"
hb = hb.replace(old_star, new_star)
print("  [OK] Replaced star emoji with SVG star")

# 1b) Border opacity tweak
old_border = 'rounded-lg border border-[#1D2A42] bg-[#0C1728] p-0.5'
new_border = 'rounded-lg border border-[#1D2A42]/50 bg-[#0C1728] p-0.5'
count = hb.count(old_border)
assert count == 1, f"Expected exactly 1 nav border occurrence, found {count}"
hb = hb.replace(old_border, new_border)
print("  [OK] Nav border opacity changed to 50%")

with open(hb_path, "w", encoding="utf-8-sig") as f:
    f.write(hb)
print("  -> HeaderBar.tsx saved")


# === 2) page.tsx changes ===
page_path = os.path.join(BASE, "app", "cn", "page.tsx")
with open(page_path, "r", encoding="utf-8-sig") as f:
    page = f.read()

# 2a) Replace sniper outer div classes with sniper-card
old_sniper = 'rounded-lg bg-[#121c2a] p-2.5 hover:bg-[#16202f] transition-colors'
new_sniper = 'sniper-card'
count = page.count(old_sniper)
assert count >= 1, f"Expected at least 1 sniper div occurrence, found {count}"
page = page.replace(old_sniper, new_sniper)
print(f"  [OK] Changed {count} sniper div(s) to sniper-card class")

# 2b) Simplify stock name font size in sniper cards
old_name = 'text-[14px] font-medium text-[#EAF2FF] hover:text-[#A78BFA] truncate'
new_name = 'text-[13px] font-medium text-[#EAF2FF] hover:text-[#A78BFA] truncate'
count = page.count(old_name)
assert count >= 1, f"Expected at least 1 stock name occurrence, found {count}"
page = page.replace(old_name, new_name)
print(f"  [OK] Simplified {count} stock name font size(s)")

with open(page_path, "w", encoding="utf-8-sig") as f:
    f.write(page)
print("  -> page.tsx saved")


# === Verification ===
print("\n=== Verification ===")
with open(hb_path, "r", encoding="utf-8-sig") as f:
    hb_check = f.read()
if '<polygon points="12 2' in hb_check:
    print("  [PASS] HeaderBar: SVG star found")
else:
    print("  [FAIL] HeaderBar: SVG star NOT found")

if 'border-[#1D2A42]/50' in hb_check:
    print("  [PASS] HeaderBar: border opacity updated")
else:
    print("  [FAIL] HeaderBar: border opacity NOT updated")

with open(page_path, "r", encoding="utf-8-sig") as f:
    page_check = f.read()
if 'className="sniper-card"' in page_check:
    print("  [PASS] page.tsx: sniper-card class found")
else:
    print("  [FAIL] page.tsx: sniper-card class NOT found")

if 'text-[13px] font-medium text-[#EAF2FF] hover:text-[#A78BFA]' in page_check:
    print("  [PASS] page.tsx: Simplified text sizes found")
else:
    print("  [FAIL] page.tsx: Simplified text sizes NOT found")

print("\n=== All changes applied successfully ===")
