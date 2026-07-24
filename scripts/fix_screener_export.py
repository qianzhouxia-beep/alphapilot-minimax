#!/usr/bin/env python3
from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / "ml_screener.py"
src = p.read_text(encoding="utf-8")
src = src.replace(
    "avail = [c for c in\nALL_FEATURES if c in latest.columns]",
    "avail = [c for c in ALL_FEATURES if c in latest.columns]",
)
if "screener = MLScreener" not in src:
    src = (
        src.rstrip()
        + "\n\n\n# Global instance used by recommend.py\n"
        + 'screener = MLScreener(model_version="v25")\n\n'
        + 'if __name__ == "__main__":\n'
        + "    print(f\"loading {screener.model_version}...\")\n"
        + "    ok = screener.load_model()\n"
        + '    print("ok" if ok else "fail", "models", len(screener.models))\n'
    )
p.write_text(src, encoding="utf-8", newline="\n")
py_compile.compile(str(p), doraise=True)
print("FIXED_OK")
