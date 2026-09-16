import json
import subprocess
import urllib.request

BODY = open("/Users/AlphaPilot/bt_research/_reply_issue6_abr_window_20260916.md",
            encoding="utf-8").read()

p = subprocess.run(["git", "credential", "fill"],
                   input=b"protocol=https\nhost=github.com\n\n",
                   capture_output=True)
tok = [l.split("=", 1)[1] for l in p.stdout.decode().splitlines()
       if l.startswith("password=")][0]

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
url = ("https://api.github.com/repos/qianzhouxia-beep/alphapilot-docs/"
       "issues/6/comments")
req = urllib.request.Request(url, method="POST",
                             data=json.dumps({"body": BODY}).encode("utf-8"))
req.add_header("Authorization", "Bearer " + tok)
req.add_header("Accept", "application/vnd.github+json")
req.add_header("User-Agent", "cursor")
req.add_header("Content-Type", "application/json")
with op.open(req, timeout=60) as x:
    d = json.loads(x.read().decode())
print("posted:", d["id"], d["html_url"])
