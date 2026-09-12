import json, subprocess, urllib.request, pathlib
p = subprocess.run(["git","credential","fill"],
                   input=b"protocol=https\nhost=github.com\n\n", capture_output=True)
tok = [l.split("=",1)[1] for l in p.stdout.decode().splitlines() if l.startswith("password=")][0]
body = pathlib.Path("/Users/AlphaPilot/bt_research/_reply_testpaths_body.md").read_text(encoding="utf-8")
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
req = urllib.request.Request(
    "https://api.github.com/repos/qianzhouxia-beep/alphapilot-docs/issues/6/comments",
    data=json.dumps({"body": body}).encode("utf-8"), method="POST")
req.add_header("Authorization", f"Bearer {tok}")
req.add_header("Accept", "application/vnd.github+json")
req.add_header("User-Agent", "cursor")
with op.open(req, timeout=30) as x:
    r = json.loads(x.read().decode())
print("posted:", r["html_url"])
