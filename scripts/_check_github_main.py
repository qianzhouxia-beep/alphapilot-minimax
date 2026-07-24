#!/usr/bin/env python3
import json
import urllib.request

url = "https://api.github.com/repos/qianzhouxia-beep/alphapilot-minimax/commits/main"
req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "alphapilot-deploy"})
with urllib.request.urlopen(req, timeout=30) as r:
    d = json.loads(r.read().decode())
print(d["sha"][:12], d["commit"]["message"].splitlines()[0], d["commit"]["author"]["date"])
