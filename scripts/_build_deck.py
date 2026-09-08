# -*- coding: utf-8 -*-
"""Generate AlphaPilot intro & promotion deck (16:9, light, financial-trust style).
Audience: mixed ages incl. elderly. Plain language + real numbers + promotion focus.
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
import copy

# ---------- palette ----------
NAVY    = RGBColor(0x0F, 0x27, 0x40)   # deep navy (cover/title)
GOLD    = RGBColor(0xC9, 0xA2, 0x27)   # trust gold
GOLD_D  = RGBColor(0x8A, 0x6D, 0x1B)
GREEN   = RGBColor(0x1B, 0x8A, 0x5A)   # positive
RED     = RGBColor(0xC0, 0x39, 0x2B)   # risk
PURPLE  = RGBColor(0x6D, 0x28, 0xD9)   # tech
INK     = RGBColor(0x1F, 0x29, 0x37)   # body text
INK_SOFT= RGBColor(0x5A, 0x66, 0x76)
BG      = RGBColor(0xF6, 0xF8, 0xFB)   # page bg
CARD    = RGBColor(0xFF, 0xFF, 0xFF)
CARD_B  = RGBColor(0xE4, 0xE9, 0xF0)
LINE    = RGBColor(0xD4, 0xDC, 0xE6)
WHITE   = RGBColor(0xFF, 0xFF, 0xFF)

FONT = "Microsoft YaHei"
FONT_EN = "Microsoft YaHei"

SW, SH = Inches(13.333), Inches(7.5)

prs = Presentation()
prs.slide_width = SW
prs.slide_height = SH
BLANK = prs.slide_layouts[6]


def _set_font(run, size, color=INK, bold=False, font=FONT):
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.name = font
    # ensure East Asian font applies too
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn('a:ea'))
    if ea is None:
        ea = rPr.makeelement(qn('a:ea'), {})
        rPr.append(ea)
    ea.set('typeface', font)


def _txt(slide, x, y, w, h, text, size=18, color=INK, bold=False,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.12):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0; tf.margin_right = 0; tf.margin_top = 0; tf.margin_bottom = 0
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        r = p.add_run(); r.text = ln
        _set_font(r, size, color, bold)
    return tb


def _rich(slide, x, y, w, h, parts, size=16, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
          line_spacing=1.15):
    """parts: list of (text, color, bold)"""
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0; tf.margin_right = 0; tf.margin_top = 0; tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = line_spacing
    for text, color, bold in parts:
        r = p.add_run(); r.text = text
        _set_font(r, size, color, bold)
    return tb


def _shape(slide, shape, x, y, w, h, fill=None, line=None, line_w=None, shadow=False):
    sp = slide.shapes.add_shape(shape, x, y, w, h)
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid(); sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = line_w or Pt(1)
    sp.shadow.inherit = False
    return sp


def _rect(slide, x, y, w, h, fill=None, line=None, line_w=None, radius=None):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    sp = _shape(slide, shape_type, x, y, w, h, fill, line, line_w)
    if radius:
        try:
            sp.adjustments[0] = radius
        except Exception:
            pass
    return sp


def _bar(slide, x, y, w, h, frac, color, bg=CARD_B):
    _rect(slide, x, y, w, h, fill=bg)
    if frac > 0:
        _rect(slide, x, y, w * frac, h, fill=color)


def _footer(slide, n):
    _txt(slide, Inches(0.45), Inches(7.08), Inches(8), Inches(0.3),
         "AlphaPilot · AI 量化投资系统", 9, INK_SOFT)
    _txt(slide, Inches(12.0), Inches(7.08), Inches(0.9), Inches(0.3),
         str(n), 9, INK_SOFT, align=PP_ALIGN.RIGHT)


def _kicker(slide, text, y=Inches(0.42)):
    _txt(slide, Inches(0.55), y, Inches(9), Inches(0.35), text, 12, GOLD_D, bold=True)


def _title(slide, text, y=Inches(0.72)):
    _txt(slide, Inches(0.55), y, Inches(12.2), Inches(0.75), text, 30, NAVY, bold=True)


def _subtitle(slide, text, y=Inches(1.42)):
    _txt(slide, Inches(0.55), y, Inches(12.2), Inches(0.45), text, 15, INK_SOFT)


# =====================================================================
# S1  cover
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=NAVY)
_rect(s, 0, Inches(5.95), SW, Inches(1.55), fill=RGBColor(0x0A, 0x1C, 0x30))
# gold accent line
_rect(s, Inches(0.9), Inches(2.52), Inches(2.2), Pt(3.2), fill=GOLD)
_txt(s, Inches(0.9), Inches(2.78), Inches(11.5), Inches(1.0),
     "AlphaPilot · AI 量化投资系统", 40, WHITE, bold=True)
_txt(s, Inches(0.9), Inches(3.7), Inches(11.5), Inches(0.9),
     "让数据替你选股，用纪律替你守住钱", 22, RGBColor(0xD8, 0xE2, 0xEF))
_txt(s, Inches(0.9), Inches(4.55), Inches(11.5), Inches(0.6),
     "一套每天扫描全市场 5000+ 只股票、自动选股、自动买卖的智能投资系统", 15, GOLD)
_txt(s, Inches(0.9), Inches(6.25), Inches(11.5), Inches(0.5),
     "给信任数据、没时间盯盘的人 —— 本次介绍约 10 分钟", 14, RGBColor(0xA9, 0xB8, 0xCC))


# =====================================================================
# S2  what we do (one sentence + 3 pillars)
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "我们做什么")
_title(s, "一句话：一套会自己学习的炒股管家")
_subtitle(s, "电脑每天从全市场 5000 多只股票里，选出最有上涨潜力的少数几只，按固定纪律买入、持有、卖出——全程不靠人的情绪和感觉。")

cards = [
    ("1", "选股模型", "每天扫描全市场\n上百个维度打分\n选出最有潜力的 Top10", NAVY),
    ("2", "买卖模型", "什么时候买、什么时候卖\n都有固定规则\n不追涨、不恐慌", GOLD_D),
    ("3", "自我进化", "每天复盘当天交易\n自动调整参数\n越用越有经验", PURPLE),
]
x0 = Inches(0.55)
cw, ch, gap = Inches(4.0), Inches(3.3), Inches(0.16)
for i, (num, t, d, c) in enumerate(cards):
    cx = x0 + i * (cw + gap)
    _rect(s, cx, Inches(2.25), cw, ch, fill=CARD, line=LINE, radius=0.06)
    _shape(s, MSO_SHAPE.OVAL, cx + Inches(0.35), Inches(2.6), Inches(0.62), Inches(0.62),
           fill=c)
    _txt(s, cx + Inches(0.35), Inches(2.72), Inches(0.62), Inches(0.4), num, 20, WHITE, bold=True,
         align=PP_ALIGN.CENTER)
    _txt(s, cx + Inches(0.35), Inches(3.5), cw - Inches(0.7), Inches(0.6), t, 19, NAVY, bold=True)
    _txt(s, cx + Inches(0.35), Inches(4.15), cw - Inches(0.7), Inches(1.4), d, 14, INK, line_spacing=1.3)

_rect(s, Inches(0.55), Inches(5.95), Inches(12.23), Inches(0.78), fill=RGBColor(0xEA, 0xF0, 0xF7), line=LINE)
_txt(s, Inches(0.85), Inches(6.1), Inches(11.7), Inches(0.5),
     "重要区别：我们和“凭感觉炒股、追涨杀跌”完全不同 —— 后面细讲。", 14, NAVY, bold=True)
_footer(s, 2)


# =====================================================================
# S3  why AI helps (human weaknesses)
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "科普：为什么需要 AI")
_title(s, "人有三个天生弱点，电脑没有")
_subtitle(s, "不是 AI 多聪明，而是它恰好补上了人最容易犯错的地方。")

rows = [
    ("情绪", "涨了想追、跌了想跑，经常卖在坑里、买在山顶", "电脑",
     "规则写死：不追高、不恐慌，说卖就卖"),
    ("体力", "一个人盯不了 5000 只股票，盯 20 只都累", "电脑",
     "每秒都在扫描全市场，不会累、不偷懒"),
    ("广度", "人只能凭经验记住几十个规律", "电脑",
     "每天用 100 多个维度给每只股票打分，公平一致"),
]
y = Inches(2.15)
rh, gap = Inches(1.42), Inches(0.18)
for i, (h_title, h_body, w_title, w_body) in enumerate(rows):
    ry = y + i * (rh + gap)
    _rect(s, Inches(0.55), ry, Inches(5.7), rh, fill=CARD, line=LINE, radius=0.07)
    _shape(s, MSO_SHAPE.OVAL, Inches(0.8), ry + Inches(0.42), Inches(0.58), Inches(0.58), fill=RED)
    _txt(s, Inches(0.8), ry + Inches(0.55), Inches(0.58), Inches(0.36), "人", 14, WHITE, bold=True, align=PP_ALIGN.CENTER)
    _txt(s, Inches(1.6), ry + Inches(0.22), Inches(4.5), Inches(0.5), h_title, 17, NAVY, bold=True)
    _txt(s, Inches(1.6), ry + Inches(0.75), Inches(4.45), Inches(0.6), h_body, 12.5, INK)

    _shape(s, MSO_SHAPE.OVAL, Inches(6.7), ry + Inches(0.42), Inches(0.58), Inches(0.58), fill=GREEN)
    _txt(s, Inches(6.7), ry + Inches(0.55), Inches(0.58), Inches(0.36), "AI", 12, WHITE, bold=True, align=PP_ALIGN.CENTER)
    _txt(s, Inches(7.5), ry + Inches(0.22), Inches(5.3), Inches(0.5), w_title, 17, NAVY, bold=True)
    _txt(s, Inches(7.5), ry + Inches(0.75), Inches(5.25), Inches(0.6), w_body, 12.5, INK)
_footer(s, 3)


# =====================================================================
# S4  how it works (pipeline)
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "科普：它怎么工作")
_title(s, "一条自动流水线：数据 → 打分 → 选股 → 买卖")
_subtitle(s, "每天不用人干预，系统自己跑完这四步。")

steps = [
    ("收集数据", "每天收盘后\n自动下载全市场\n行情、资金、消息", NAVY),
    ("给股票打分", "每只股票用\n100+ 个维度打分\n排出潜力顺序", GOLD_D),
    ("选出候选", "只留最有把握的\n前 10 名，宁缺毋滥\n不搞广撒网", PURPLE),
    ("按纪律买卖", "买点出现才买\n每天最多 2 只\n止损止盈有规则", GREEN),
]
x0 = Inches(0.55)
cw, ch, gap = Inches(2.95), Inches(3.4), Inches(0.12)
for i, (t, d, c) in enumerate(steps):
    cx = x0 + i * (cw + gap)
    _rect(s, cx, Inches(2.35), cw, ch, fill=CARD, line=LINE, radius=0.06)
    _rect(s, cx, Inches(2.35), cw, Inches(0.55), fill=c, radius=0.06)
    _txt(s, cx + Inches(0.15), Inches(2.44), cw - Inches(0.3), Inches(0.4), t, 15, WHITE, bold=True)
    _txt(s, cx + Inches(0.2), Inches(3.2), cw - Inches(0.4), Inches(2.2), d, 13, INK, line_spacing=1.35)

_rect(s, Inches(0.55), Inches(6.05), Inches(12.23), Inches(0.7), fill=RGBColor(0xEA, 0xF0, 0xF7), line=LINE)
_txt(s, Inches(0.85), Inches(6.2), Inches(11.7), Inches(0.45),
     "关键：先在全市场“大海捞针”，再按纪律出手——不是猜，是按数据说话。", 13.5, NAVY, bold=True)
_footer(s, 4)


# =====================================================================
# S5  vs institutional quant (our edge)  ★ user emphasized
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "我们和机构量化有什么不一样")
_title(s, "同样用 AI，我们专为个人投资者设计")
_subtitle(s, "机构量化很好，但那是给大资金玩的；我们的优势，正是它们做不到的。")

left = [
    ("机构量化", RED),
    ("门槛高：多数 100 万起，个人够不着", RED),
    ("策略黑箱：你永远不知道它在买什么", RED),
    ("拼速度抢单：赚快钱，普通人学不会", RED),
    ("服务大资金：你的几万块不值得理", RED),
]
right = [
    ("AlphaPilot（我们）", GREEN),
    ("门槛低：小资金也能参与", GREEN),
    ("全透明：每天买了什么、为什么买，都能查", GREEN),
    ("拼眼光选股：更关心“选得对不对”", GREEN),
    ("为你服务：专做 A 股个人投资者", GREEN),
]
# left card
_rect(s, Inches(0.55), Inches(2.15), Inches(5.9), Inches(4.3), fill=CARD, line=LINE, radius=0.05)
_rect(s, Inches(0.55), Inches(2.15), Inches(5.9), Inches(0.7), fill=RGBColor(0xFB, 0xE9, 0xE7), line=LINE)
_txt(s, Inches(0.85), Inches(2.28), Inches(5.4), Inches(0.45), left[0][0], 18, RED, bold=True)
for i, (txt, col) in enumerate(left[1:], 1):
    _txt(s, Inches(0.85), Inches(3.0 + (i - 1) * 0.82), Inches(5.3), Inches(0.7), "✗  " + txt, 14, INK)
# right card
_rect(s, Inches(6.9), Inches(2.15), Inches(5.9), Inches(4.3), fill=RGBColor(0xEA, 0xF5, 0xEF), line=GREEN, line_w=Pt(1.2))
_rect(s, Inches(6.9), Inches(2.15), Inches(5.9), Inches(0.7), fill=RGBColor(0xD5, 0xEA, 0xDE), line=GREEN)
_txt(s, Inches(7.2), Inches(2.28), Inches(5.4), Inches(0.45), right[0][0], 18, GREEN, bold=True)
for i, (txt, col) in enumerate(right[1:], 1):
    _txt(s, Inches(7.2), Inches(3.0 + (i - 1) * 0.82), Inches(5.3), Inches(0.7), "✓  " + txt, 14, INK)
_footer(s, 5)


# =====================================================================
# S6  why it wins 1: picks well (selection)
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "凭什么能赚钱 · 第一点")
_title(s, "选得准：全市场“大海捞针”，只挑最有把握的")
_subtitle(s, "选股质量决定收益的大头。我们的模型不是推荐“会涨的股票”，而是筛掉“大概率会跌的”。")

# stat cards
stats = [
    ("5000+", "每天扫描的股票数\n相当于一个人盯 250 天", NAVY),
    ("100+", "每只股票打分的维度\n价格、资金、消息、筹码…", GOLD_D),
    ("Top10", "每天只留最有把握的 10 只\n宁缺毋滥", PURPLE),
    ("3 次验证", "选出的股票要过 3 道门槛\n模型分 + 资金 + 盘面确认", GREEN),
]
x0 = Inches(0.55)
cw, ch = Inches(3.0), Inches(2.1)
gap = Inches(0.08)
for i, (num, d, c) in enumerate(stats):
    cx = x0 + i * (cw + gap)
    _rect(s, cx, Inches(2.2), cw, ch, fill=CARD, line=LINE, radius=0.07)
    _txt(s, cx + Inches(0.2), Inches(2.5), cw - Inches(0.4), Inches(0.7), num, 30, c, bold=True)
    _txt(s, cx + Inches(0.2), Inches(3.3), cw - Inches(0.4), Inches(0.9), d, 12.5, INK, line_spacing=1.25)

# number proof bar
_rect(s, Inches(0.55), Inches(4.75), Inches(12.23), Inches(1.95), fill=CARD, line=LINE, radius=0.06)
_txt(s, Inches(0.85), Inches(4.95), Inches(11.6), Inches(0.45),
     "数字证明：同样的选股信号，加一道“资金确认门槛”后", 15, NAVY, bold=True)
# bar 1
_txt(s, Inches(0.85), Inches(5.5), Inches(3.0), Inches(0.4), "不加门槛 胜率 42.3%", 12.5, INK_SOFT)
_bar(s, Inches(4.0), Inches(5.55), Inches(4.6), Inches(0.32), 0.423, RED)
# bar 2
_txt(s, Inches(0.85), Inches(6.0), Inches(3.0), Inches(0.4), "加门槛后 胜率 54.2%", 12.5, INK)
_bar(s, Inches(4.0), Inches(6.05), Inches(4.6), Inches(0.32), 0.542, GREEN)
_txt(s, Inches(8.8), Inches(5.5), Inches(3.6), Inches(0.9),
     "同一个模型，多一道筛选，\n胜率提升近 12 个百分点。", 12.5, GOLD_D, bold=True, line_spacing=1.3)
_footer(s, 6)


# =====================================================================
# S7  why it wins 2: buys disciplined
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "凭什么能赚钱 · 第二点")
_title(s, "买得稳：宁可错过，也不乱买")
_subtitle(s, "最伤钱的不是“没买”，而是“追高买在山顶”。我们有 4 道刹车。")

guards = [
    ("不追高", "当天涨幅超过一定\n幅度，直接跳过\n涨停的股票一律不追", RED),
    ("看资金", "要看到真金白银\n流入才买\n不是只看 K 线好看", GOLD_D),
    ("看换手", "换手太高的不碰\n那是“人气过热”\n风险远大于机会", PURPLE),
    ("限次数", "一天最多买 2 只\n仓位严格限制\n永远给自己留余地", GREEN),
]
x0 = Inches(0.55)
cw, ch, gap = Inches(3.0), Inches(3.5), Inches(0.08)
for i, (t, d, c) in enumerate(guards):
    cx = x0 + i * (cw + gap)
    _rect(s, cx, Inches(2.3), cw, ch, fill=CARD, line=LINE, radius=0.06)
    _rect(s, cx, Inches(2.3), cw, Inches(0.5), fill=c, radius=0.06)
    _txt(s, cx + Inches(0.15), Inches(2.38), cw - Inches(0.3), Inches(0.38), t, 15, WHITE, bold=True)
    _txt(s, cx + Inches(0.2), Inches(3.1), cw - Inches(0.4), Inches(2.4), d, 13, INK, line_spacing=1.35)

_rect(s, Inches(0.55), Inches(6.1), Inches(12.23), Inches(0.68), fill=RGBColor(0xEA, 0xF0, 0xF7), line=LINE)
_txt(s, Inches(0.85), Inches(6.25), Inches(11.7), Inches(0.45),
     "数字证明：换手率极低的票（还没被爆炒）平均收益 +5.8%，胜率 92.7%；换手过热的票平均亏损。", 13, NAVY, bold=True)
_footer(s, 7)


# =====================================================================
# S8  why it wins 3: sells by rules
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "凭什么能赚钱 · 第三点")
_title(s, "卖得有纪律：该跑就跑，不跟股票谈恋爱")
_subtitle(s, "散户最容易亏钱的两个动作：亏了死扛、赚了拿不住。我们用规则解决。")

rules = [
    ("止损", "买错了不硬扛\n回撤到设定比例\n自动卖出，先保本金", RED),
    ("止盈", "赚到目标收益\n分批卖出落袋\n不贪最后一个铜板", GOLD_D),
    ("到期必走", "持有到 T+2 天\n无论盈亏按计划处理\n不留“等回本”的侥幸", PURPLE),
]
x0 = Inches(0.55)
cw, ch, gap = Inches(4.0), Inches(3.1), Inches(0.16)
for i, (t, d, c) in enumerate(rules):
    cx = x0 + i * (cw + gap)
    _rect(s, cx, Inches(2.3), cw, ch, fill=CARD, line=LINE, radius=0.06)
    _shape(s, MSO_SHAPE.OVAL, cx + Inches(0.3), Inches(2.65), Inches(0.6), Inches(0.6), fill=c)
    _txt(s, cx + Inches(0.3), Inches(2.78), Inches(0.6), Inches(0.4), str(i + 1), 18, WHITE, bold=True, align=PP_ALIGN.CENTER)
    _txt(s, cx + Inches(0.3), Inches(3.55), cw - Inches(0.6), Inches(0.5), t, 18, NAVY, bold=True)
    _txt(s, cx + Inches(0.3), Inches(4.15), cw - Inches(0.6), Inches(1.1), d, 13, INK, line_spacing=1.3)

_rect(s, Inches(0.55), Inches(5.8), Inches(12.23), Inches(0.9), fill=RGBColor(0xEA, 0xF0, 0xF7), line=LINE)
_txt(s, Inches(0.85), Inches(5.95), Inches(11.7), Inches(0.6),
     "我们专门研究过：卖出规则改对了，能把“卖飞”减少一半以上——\n比如给弱势卖出信号加一道“次日确认”，避免卖完就大涨的尴尬。", 13, NAVY, bold=True, line_spacing=1.25)
_footer(s, 8)


# =====================================================================
# S9  why it wins 4: self-improvement
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "凭什么能赚钱 · 第四点")
_title(s, "会进化：每天复盘，越用越有经验")
_subtitle(s, "这是我们和普通炒股软件最本质的区别——它会从自己的交易结果里学习。")

# left: explain loop
_rect(s, Inches(0.55), Inches(2.2), Inches(6.3), Inches(4.4), fill=CARD, line=LINE, radius=0.05)
_txt(s, Inches(0.85), Inches(2.45), Inches(5.7), Inches(0.5), "每天自动跑的学习闭环", 18, NAVY, bold=True)
loop = [
    ("记录", "把当天的买卖结果\n（赚了还是亏了）记下来"),
    ("统计", "算出每类信号\n到底准不准"),
    ("调整", "表现好的信号多给权重\n表现差的自动降权"),
    ("明天更好", "第二天用新参数继续\n每天都比昨天更聪明"),
]
ly = Inches(3.1)
for i, (t, d) in enumerate(loop):
    _shape(s, MSO_SHAPE.OVAL, Inches(0.9), ly + i * Inches(0.95) - Inches(0.1), Inches(0.5), Inches(0.5),
           fill=[NAVY, GOLD_D, PURPLE, GREEN][i])
    _txt(s, Inches(0.9), ly + i * Inches(0.95), Inches(0.5), Inches(0.3), str(i + 1), 13, WHITE, bold=True, align=PP_ALIGN.CENTER)
    _txt(s, Inches(1.6), ly + i * Inches(0.95) - Inches(0.08), Inches(5.1), Inches(0.4), t, 15, NAVY, bold=True)
    _txt(s, Inches(1.6), ly + i * Inches(0.95) + Inches(0.28), Inches(5.1), Inches(0.55), d, 12.5, INK, line_spacing=1.15)

# right: today's real example
_rect(s, Inches(7.1), Inches(2.2), Inches(5.7), Inches(4.4), fill=RGBColor(0xEA, 0xF5, 0xEF), line=GREEN, line_w=Pt(1.2))
_txt(s, Inches(7.4), Inches(2.45), Inches(5.1), Inches(0.5), "今天的真实例子（2026-08-31）", 16, GREEN, bold=True)
_txt(s, Inches(7.4), Inches(3.1), Inches(5.1), Inches(0.9),
     "系统发现近 9 天里，“ICIR 资金强度因子”有 6 天预测方向是对的（正确率 67%），于是把它的权重从 0.50 自动上调到 0.55。",
     13, INK, line_spacing=1.3)
_rect(s, Inches(7.4), Inches(4.6), Inches(5.0), Inches(1.4), fill=WHITE, line=GREEN)
_txt(s, Inches(7.6), Inches(4.75), Inches(4.6), Inches(0.4), "权重调整记录", 12.5, GREEN, bold=True)
_txt(s, Inches(7.6), Inches(5.15), Inches(4.6), Inches(0.75),
     "W_ICIR：0.50 → 0.55（自动）\n选股 37 只，当日 IC 相关度 +0.233", 12.5, INK, line_spacing=1.3)
_footer(s, 9)


# =====================================================================
# S10  real numbers (sim account)
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "数字说话 · 全部来自真实记录")
_title(s, "先别信“策略”，先看“账本”")
_subtitle(s, "以下都是模拟盘和回测的真实记录，不是 PPT 编的数字。")

# left big stat
_rect(s, Inches(0.55), Inches(2.2), Inches(6.0), Inches(4.5), fill=NAVY, radius=0.05)
_txt(s, Inches(0.95), Inches(2.55), Inches(5.2), Inches(0.45), "系统内部模拟账本（自动记录、可复核）", 14, RGBColor(0xD8, 0xE2, 0xEF))
_txt(s, Inches(0.95), Inches(3.05), Inches(5.2), Inches(1.1), "累计收益 ≈ +4.8 万元", 34, GOLD, bold=True)
_txt(s, Inches(0.95), Inches(4.15), Inches(5.2), Inches(0.45), "来自最近 23 笔已结算交易", 14, WHITE, bold=True)
_txt(s, Inches(0.95), Inches(4.6), Inches(5.2), Inches(0.45), "胜率 52%，盈亏比健康", 14, RGBColor(0xD8, 0xE2, 0xEF))
_rect(s, Inches(0.95), Inches(5.35), Inches(5.2), Inches(1.0), fill=RGBColor(0x0A, 0x1C, 0x30))
_txt(s, Inches(1.2), Inches(5.5), Inches(4.8), Inches(0.85),
     "这是系统内部模拟盘的记录，不是真实资金。\n意义在于：每一步都有据可查，可以随时复核。",
     12, RGBColor(0xA9, 0xB8, 0xCC), line_spacing=1.25)

# right verification ladder
_rect(s, Inches(6.9), Inches(2.2), Inches(5.9), Inches(4.5), fill=CARD, line=LINE, radius=0.05)
_txt(s, Inches(7.2), Inches(2.45), Inches(5.4), Inches(0.5), "我们怎么证明“不是吹的”", 18, NAVY, bold=True)
ladder = [
    ("第一步 历史回测", "拿过去几个月全市场数据\n验证策略在历史行情中的表现"),
    ("第二步 模拟盘跑", "像真钱一样在模拟盘交易\n记录每一笔，可查"),
    ("第三步 实盘小规模", "通过前两步才考虑上实盘\n用小资金，边跑边观察"),
]
ly = Inches(3.2)
for i, (t, d) in enumerate(ladder):
    _rect(s, Inches(7.2), ly + i * Inches(1.15), Inches(5.3), Inches(1.0), fill=BG, line=LINE, radius=0.08)
    _txt(s, Inches(7.4), ly + i * Inches(1.15) + Inches(0.12), Inches(4.9), Inches(0.4), t, 13.5, NAVY, bold=True)
    _txt(s, Inches(7.4), ly + i * Inches(1.15) + Inches(0.5), Inches(4.9), Inches(0.45), d, 11.5, INK, line_spacing=1.15)
_footer(s, 10)


# =====================================================================
# S11  risk control first
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "风控第一")
_title(s, "我们首先想的不是赚多少，而是亏多少")
_subtitle(s, "投资最重要的不是收益，是“永远有下一次机会”。下面每条都是硬规则。")

rcs = [
    ("仓位控制", "一只股票最多只占总资产 15%\n鸡蛋不放一个篮子里", NAVY),
    ("每天限量", "一天最多买 2 只\n不因行情好就上头加仓", GOLD_D),
    ("持仓上限", "最多同时持有 4 只\n仓位永远留有余地", PURPLE),
    ("市场门控", "市场太差的日子\n自动降仓位甚至空仓\n不硬着头皮交易", GREEN),
]
x0 = Inches(0.55)
cw, ch, gap = Inches(3.0), Inches(2.6), Inches(0.08)
for i, (t, d, c) in enumerate(rcs):
    cx = x0 + i * (cw + gap)
    _rect(s, cx, Inches(2.25), cw, ch, fill=CARD, line=LINE, radius=0.06)
    _rect(s, cx, Inches(2.25), cw, Inches(0.5), fill=c, radius=0.06)
    _txt(s, cx + Inches(0.15), Inches(2.33), cw - Inches(0.3), Inches(0.38), t, 15, WHITE, bold=True)
    _txt(s, cx + Inches(0.2), Inches(3.0), cw - Inches(0.4), Inches(1.7), d, 12.5, INK, line_spacing=1.3)

_rect(s, Inches(0.55), Inches(5.35), Inches(12.23), Inches(1.25), fill=RGBColor(0xFB, 0xE9, 0xE7), line=RED, line_w=Pt(1.2))
_txt(s, Inches(0.85), Inches(5.55), Inches(11.7), Inches(0.9),
     "诚实说明：任何策略都有亏钱的可能，市场有系统性风险（如股灾）。我们能做的是把单次亏损控制在小范围、把“长期活下去”作为第一目标，而不是承诺一定赚钱。",
     13.5, INK, bold=True, line_spacing=1.3)
_footer(s, 11)


# =====================================================================
# S12  transparency (why trust us)
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "信任从哪里来")
_title(s, "我们敢把账本摊开给你看")
_subtitle(s, "所有交易记录、选股记录、参数调整，都是可查证的。")

trust = [
    ("每一笔交易都可查", "买了什么、什么价格、什么理由\n全部自动记录，随时可以看", NAVY),
    ("每一天选股都存档", "昨天选了哪 10 只\n明天就能验证它对不对", GOLD_D),
    ("每一次调整都有日志", "权重为什么改、改了多少\n白纸黑字写下来", PURPLE),
    ("验证过的才上实盘", "模拟盘没跑够、回测没通过\n绝不拿去用真钱试", GREEN),
]
x0 = Inches(0.55)
cw, ch, gap = Inches(3.0), Inches(3.6), Inches(0.08)
for i, (t, d, c) in enumerate(trust):
    cx = x0 + i * (cw + gap)
    _rect(s, cx, Inches(2.25), cw, ch, fill=CARD, line=LINE, radius=0.06)
    _shape(s, MSO_SHAPE.OVAL, cx + Inches(0.3), Inches(2.6), Inches(0.6), Inches(0.6), fill=c)
    _txt(s, cx + Inches(0.3), Inches(2.73), Inches(0.6), Inches(0.4), "✓", 18, WHITE, bold=True, align=PP_ALIGN.CENTER)
    _txt(s, cx + Inches(0.3), Inches(3.45), cw - Inches(0.6), Inches(0.9), t, 16, NAVY, bold=True, line_spacing=1.2)
    _txt(s, cx + Inches(0.3), Inches(4.4), cw - Inches(0.6), Inches(1.3), d, 12.5, INK, line_spacing=1.3)

_rect(s, Inches(0.55), Inches(6.15), Inches(12.23), Inches(0.6), fill=RGBColor(0xEA, 0xF0, 0xF7), line=LINE)
_txt(s, Inches(0.85), Inches(6.27), Inches(11.7), Inches(0.4),
     "信任不是靠嘴上保证，是靠每天都能复核的记录。", 13.5, NAVY, bold=True)
_footer(s, 12)


# =====================================================================
# S13  promotion: how to talk about it  ★ focus
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "怎么跟人讲（推广重点）")
_title(s, "三句话介绍，谁都能听懂")
_subtitle(s, "不要讲技术，讲“能帮你解决什么问题”。")

# 3 sentence cards
phrases = [
    ("第一句", "电脑每天把全市场 5000 多只股票\n全看一遍，选出最有把握的几只"),
    ("第二句", "买什么、什么时候买、什么时候卖\n都是电脑按规则来，不靠感觉"),
    ("第三句", "它每天还自己复盘、自己进步\n相当于一个 24 小时在岗的基金经理"),
]
x0 = Inches(0.55)
cw, ch, gap = Inches(4.0), Inches(2.5), Inches(0.16)
for i, (t, d) in enumerate(phrases):
    cx = x0 + i * (cw + gap)
    _rect(s, cx, Inches(2.15), cw, ch, fill=CARD, line=LINE, radius=0.06)
    _txt(s, cx + Inches(0.25), Inches(2.45), cw - Inches(0.5), Inches(0.45), t, 15, GOLD_D, bold=True)
    _txt(s, cx + Inches(0.25), Inches(3.0), cw - Inches(0.5), Inches(1.5), d, 15, INK, bold=True, line_spacing=1.4)

# objections & answers
_rect(s, Inches(0.55), Inches(5.0), Inches(12.23), Inches(1.7), fill=CARD, line=LINE, radius=0.05)
_txt(s, Inches(0.85), Inches(5.15), Inches(11.6), Inches(0.4), "对方可能会问：", 14, NAVY, bold=True)
qa = [
    ("“会不会亏？”", "会，任何投资都有风险。但每笔控制在 15% 仓位以内，市场差自动降仓。"),
    ("“你自己怎么不保证赚钱？”", "正因为我们不承诺，才更值得信——承诺保本的才是骗子。"),
    ("“跟买基金有什么区别？”", "基金是给你一篮子股票，我们是用 AI 帮你挑时机，并且完全透明。"),
]
for i, (q, a) in enumerate(qa):
    qx = Inches(0.85) + i * Inches(4.0)
    _txt(s, qx, Inches(5.6), Inches(3.8), Inches(0.4), q, 13, GOLD_D, bold=True)
    _txt(s, qx, Inches(6.0), Inches(3.8), Inches(0.7), a, 11.5, INK, line_spacing=1.2)
_footer(s, 13)


# =====================================================================
# S14  how to get involved (call to action)
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=BG)
_kicker(s, "怎么参与")
_title(s, "建议的参与方式：先看，再试，后加")
_subtitle(s, "不急着掏钱。我们用三个步骤，让信任自然建立。")

steps = [
    ("看记录", "先看过去几周的选股和\n交易记录，验证是不是\n真的像说的那样", NAVY),
    ("小额试跑", "拿一小笔闲置资金试跑\n亲身体验买卖的\n过程和频率", GOLD_D),
    ("逐步加仓", "对体验满意后再考虑\n加大投入\n每一步都有记录可查", GREEN),
]
x0 = Inches(0.55)
cw, ch, gap = Inches(4.0), Inches(2.9), Inches(0.16)
for i, (t, d, c) in enumerate(steps):
    cx = x0 + i * (cw + gap)
    _rect(s, cx, Inches(2.3), cw, ch, fill=CARD, line=LINE, radius=0.06)
    _shape(s, MSO_SHAPE.OVAL, cx + Inches(0.3), Inches(2.65), Inches(0.62), Inches(0.62), fill=c)
    _txt(s, cx + Inches(0.3), Inches(2.78), Inches(0.62), Inches(0.4), str(i + 1), 18, WHITE, bold=True, align=PP_ALIGN.CENTER)
    _txt(s, cx + Inches(0.3), Inches(3.6), cw - Inches(0.6), Inches(0.5), t, 18, NAVY, bold=True)
    _txt(s, cx + Inches(0.3), Inches(4.2), cw - Inches(0.6), Inches(0.9), d, 13, INK, line_spacing=1.3)

_rect(s, Inches(0.55), Inches(5.6), Inches(12.23), Inches(1.0), fill=RGBColor(0xEA, 0xF0, 0xF7), line=LINE)
_txt(s, Inches(0.85), Inches(5.78), Inches(11.7), Inches(0.7),
     "最适合的人群：有一定闲钱、想理财但没时间盯盘、受够了自己炒股亏钱的人。\n不适合的人群：想一夜暴富、接受不了任何波动的人。",
     13.5, NAVY, bold=True, line_spacing=1.3)
_footer(s, 14)


# =====================================================================
# S15  closing
# =====================================================================
s = prs.slides.add_slide(BLANK)
_rect(s, 0, 0, SW, SH, fill=NAVY)
_rect(s, 0, Inches(6.0), SW, Inches(1.5), fill=RGBColor(0x0A, 0x1C, 0x30))
_rect(s, Inches(0.9), Inches(2.5), Inches(2.2), Pt(3.2), fill=GOLD)
_txt(s, Inches(0.9), Inches(2.78), Inches(11.5), Inches(0.9),
     "一句话总结", 34, WHITE, bold=True)
_txt(s, Inches(0.9), Inches(3.62), Inches(11.5), Inches(0.9),
     "用数据代替感觉，用纪律代替冲动，用复盘代替运气。", 22, GOLD)
_txt(s, Inches(0.9), Inches(4.55), Inches(11.5), Inches(0.7),
     "我们不承诺你赚钱，只承诺：每一步都有记录，每一个数字都经得起核对。", 15, RGBColor(0xD8, 0xE2, 0xEF))
_txt(s, Inches(0.9), Inches(6.25), Inches(11.5), Inches(0.5),
     "想了解更多 → 随时可以看我们的每日选股和交易记录", 14, RGBColor(0xA9, 0xB8, 0xCC))


out = r"C:\Users\elvisq\Projects\alphapilot\docs\AlphaPilot_AI量化投资系统_介绍与推广.pptx"
prs.save(out)
print("saved", out, "slides", len(prs.slides.__iter__.__self__._sldIdLst))
