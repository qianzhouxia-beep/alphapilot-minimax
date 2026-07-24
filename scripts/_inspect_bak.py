from pathlib import Path

raw = Path("ml_screener.py.bak_before_p0").read_bytes()
text = raw.decode("utf-16-le")
idx = text.find("score_stock")
print("idx", idx)
snippet = text[idx : idx + 600]
print(repr(snippet[:450]))
