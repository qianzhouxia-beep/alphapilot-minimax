#!/usr/bin/env python3
"""Patch Zeabur CN page: replace 自我进化学习 with R&D dual-loop selling point."""
from pathlib import Path

path = Path("/home/ubuntu/alphapilot-repo/frontend/app/cn/page.tsx")
text = path.read_text(encoding="utf-8")

old_start = '      <section className="mb-6">\n        <div className="flex items-center gap-3 mb-4">\n          <div className="w-1 h-6 rounded-full bg-status-success"></div>\n          <h2 className="text-[18px] font-semibold text-text-primary">自我进化学习</h2>'
if old_start not in text:
    raise SystemExit("anchor not found")

# find section end before footer
idx = text.find(old_start)
footer = text.find('      <footer className="mt-10 text-center text-[11px] text-text-disabled">', idx)
if footer < 0:
    raise SystemExit("footer not found")

new = '''      <section className="mb-6">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-1 h-6 rounded-full bg-status-success"></div>
          <h2 className="text-[18px] font-semibold text-text-primary">模型研发双循环</h2>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-status-success/12 text-status-success border border-[rgba(62,230,168,0.25)]">R&amp;D Workshop</span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-status-info/12 text-status-info border border-[rgba(77,163,255,0.25)]">与交易分轨</span>
        </div>
        <p className="mb-4 text-[12px] text-text-secondary leading-relaxed max-w-3xl">
          AlphaPilot 把「选股交易」和「模型研发」拆成两个独立部门：研发侧自动提出因子假设、生成代码并回测；
          只有通过可交易验证并经人工对照现网模型后，才会晋升上线——交易链路不会被实验干扰。
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3 mb-3">
          <div className="rounded-2xl border border-border-subtle bg-surface-card p-4 card-lift shadow-sm border-t-2 border-t-purple-primary">
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">Track A · 现网增益</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              每周在现有 VM2.5 特征空间自动挖掘增量因子，候选重训并对齐可交易 OOS，专为抬升当前生产模型。
            </p>
          </div>
          <div className="rounded-2xl border border-border-subtle bg-surface-card p-4 card-lift shadow-sm border-t-2 border-t-status-success">
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">Track B · RD 自研</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              RD-Agent 独立提出假设、写因子代码并回测，探索现网特征之外的新结构；导出后再接入同一晋升闸门。
            </p>
          </div>
          <div className="rounded-2xl border border-border-subtle bg-surface-card p-4 card-lift shadow-sm border-t-2 border-t-status-warning">
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">晋升闸门 · 人工终审</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              候选模型必须过可交易回测，并与生产模型对比；禁止自动热切换。审核通过才安装进线上打分槽位。
            </p>
          </div>
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg bg-surface-container-low px-3 py-2.5 border border-border-subtle">
          <p className="text-[12px] text-text-secondary">
            <span className="text-text-primary">时间表</span>
            ：周六 02:00 Track A 候选训练 · 工作日人工对照生产 OOS · 通过后才晋升 · 盘中交易链不受研发任务干扰
          </p>
        </div>
      </section>

'''

path.write_text(text[:idx] + new + text[footer:], encoding="utf-8")
print("patched", path)
assert "模型研发双循环" in path.read_text(encoding="utf-8")
