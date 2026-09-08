# -*- coding: utf-8 -*-
"""打包 AlphaPilot 核心模型+代码+文档为 tar.gz（供备份到新加坡服务器）"""
import os
import sys
import tarfile
import datetime

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = r"C:\Users\elvisq\Projects\alphapilot"
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = os.path.join(ROOT, f"backup_alphapilot_{STAMP}.tar.gz")

# 需要打包的顶层内容
INCLUDE_TOPDIRS = [
    "models",
    "production_strategies",
    "knowledge",
    "docs",
    "scripts",
    "bt_research",
    "data",
    "research",
    "crypto",
]
INCLUDE_FILES = [
    "AGENTS.md",
    "CONTEXT-MAP.md",
    "MEMORY.md",
    "README.md",
]

# data 里排除的目录（原始K线缓存等大文件，不属于模型/文档核心）
DATA_EXCLUDE_DIRS = {"kline_cache", "kline5m_hist", "__pycache__"}


def should_skip(arcname: str) -> bool:
    parts = arcname.replace("\\", "/").split("/")
    for p in parts:
        if p == "__pycache__":
            return True
        if p == ".git":
            return True
        if p in (".ipynb_checkpoints",):
            return True
    # data 子目录排除
    if len(parts) > 2 and parts[0] == "data" and parts[1] in DATA_EXCLUDE_DIRS:
        return True
    return False


def main() -> int:
    count = 0
    size = 0
    with tarfile.open(OUT, "w:gz") as tf:
        for d in INCLUDE_TOPDIRS:
            src = os.path.join(ROOT, d)
            if not os.path.isdir(src):
                print(f"!! 目录不存在: {d}")
                continue
            for root, dirs, files in os.walk(src):
                # 原地过滤：移除应排除的目录，避免深入
                dirs[:] = [x for x in dirs if not should_skip(os.path.join(root, x))]
                for f in files:
                    fp = os.path.join(root, f)
                    arcname = os.path.relpath(fp, ROOT)
                    if should_skip(arcname):
                        continue
                    try:
                        tf.add(fp, arcname=arcname)
                        count += 1
                        size += os.path.getsize(fp)
                    except Exception as e:
                        print(f"  跳过 {arcname}: {str(e)[:60]}")
        for f in INCLUDE_FILES:
            fp = os.path.join(ROOT, f)
            if os.path.isfile(fp):
                try:
                    tf.add(fp, arcname=f)
                    count += 1
                    size += os.path.getsize(fp)
                except Exception as e:
                    print(f"  跳过 {f}: {str(e)[:60]}")

    mb = size / 1024 / 1024
    out_mb = os.path.getsize(OUT) / 1024 / 1024
    print(f"打包完成: {count} 文件, {mb:.1f}MB 原始 -> {out_mb:.1f}MB tar.gz")
    print(f"输出: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
