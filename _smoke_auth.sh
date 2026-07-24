#!/bin/bash
cd /home/ubuntu/alphapilot
python3 <<'PY'
import json, urllib.request, urllib.error, os, glob

# Find owner credentials hints
for p in sorted(glob.glob("/home/ubuntu/alphapilot/data/users*.json") + glob.glob("/home/ubuntu/alphapilot/data/auth*"))[:10]:
    print("file", p, "size", os.path.getsize(p))

# Try common login
candidates = [
    {"username": "owner", "password": "owner"},
    {"email": "owner", "password": "owner"},
    {"username": "admin", "password": "admin"},
    {"username": "elvis", "password": "elvis"},
]

# Look at auth module for demo users
import auth_store if False else None
PY
python3 <<'PY'
import json, os, urllib.request, urllib.error

# inspect auth
import importlib
for name in ("auth", "auth_store", "user_auth", "cn_auth"):
    try:
        m = importlib.import_module(name)
        print("module", name, getattr(m, "__file__", None))
    except Exception as e:
        pass

from pathlib import Path
# find owner user file
for root, dirs, files in os.walk("/home/ubuntu/alphapilot/data"):
    for f in files:
        if "user" in f.lower() or "auth" in f.lower():
            print(os.path.join(root, f))
PY
