import os
BASE = r"D:\AI\alphapilot\部署文件\frontend"

with open(os.path.join(BASE, "components", "HeaderBar.tsx"), "r", encoding="utf-8-sig") as f:
    hb = f.read()

with open(os.path.join(BASE, "app", "cn", "page.tsx"), "r", encoding="utf-8-sig") as f:
    page = f.read()

print("=== Final Verification ===")
checks = [
    ("HeaderBar SVG star", 'polygon points="12 2"' in hb),
    ("HeaderBar border opacity 50%", "/50 bg-[#0C1728] p-0.5" in hb),
    ("HeaderBar old emoji removed", "\u2b50" not in hb),
    ("page.tsx sniper-card", 'className="sniper-card"' in page),
    ("page.tsx simplified name size", 'text-[13px] font-medium text-[#EAF2FF]' in page),
]
all_ok = True
for name, ok in checks:
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  [{status}] {name}")

print(f"\n  All checks: {'PASS' if all_ok else 'FAIL'}")
