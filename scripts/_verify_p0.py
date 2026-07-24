from pathlib import Path

checks = {
    "recommend v25": 'load_model(version="v25")' in Path("recommend.py").read_text(encoding="utf-8"),
    "ml _load_v25": "def _load_v25" in Path("ml_screener.py").read_text(encoding="utf-8"),
    "ml _score_v25": "def _score_v25" in Path("ml_screener.py").read_text(encoding="utf-8"),
    "money hard": "hard_main_net_5d" in Path("money_flow_gate.py").read_text(encoding="utf-8"),
    "soft off": "ENABLE_SOFT_INTRADAY" in Path("alphapilot_pipeline_v3.py").read_text(encoding="utf-8"),
    "no gc fallback": "不回退全量推荐" in Path("alphapilot_pipeline_v3.py").read_text(encoding="utf-8"),
}
for k, v in checks.items():
    print(("OK" if v else "FAIL"), k)
raise SystemExit(0 if all(checks.values()) else 1)
