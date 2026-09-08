#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlphaPilot 框架概述 — 中文宣传 PDF

设计风格：匹配 AlphaPilot 网页暗色金融风
- 背景色: #0A1628 / #0C1728
- 主色调: #4DA3FF (品牌蓝) / #7ddeff / #3EE6A8 (涨绿)
- 文字: #EAF2FF / #9FB0C7 / #6E7C93
- 包含流程图、Logo、装饰元素
- 不涉及核心算法细节
"""
from fpdf import FPDF
from pathlib import Path
import os

OUT = Path(__file__).resolve().parent / "AlphaPilot_Framework_CN.pdf"
ROOT = Path(__file__).resolve().parents[1]
LOGO_PATH = ROOT / "_brand_logo.png"
BULL_PATH = ROOT / "_golden_bull.png"

# ── 品牌色 ──
BG_DARK   = (10, 22, 40)     # #0A1628
BG_CARD   = (12, 23, 40)     # #0C1728
BG_CARD2  = (18, 32, 52)     # slightly lighter card
BORDER    = (29, 42, 66)     # #1D2A42
BLUE      = (77, 163, 255)   # #4DA3FF
BLUE_LT   = (125, 222, 255)  # #7ddeff
BLUE_DK   = (0, 49, 91)      # #00315b
GREEN     = (62, 230, 168)   # #3EE6A8
GOLD      = (245, 196, 81)   # #F5C451
RED       = (255, 93, 93)    # #FF5D5D
PURPLE    = (167, 139, 250)  # #A78BFA
TEXT_PRI  = (234, 242, 255)  # #EAF2FF
TEXT_SEC  = (159, 176, 199)  # #9FB0C7
TEXT_MUT  = (110, 124, 147)  # #6E7C93

# CJK font
_CJK_FONT = "C:/Windows/Fonts/msyh.ttc"


def _hex(c):
    """color tuple to hex for drawing"""
    return "#{:02X}{:02X}{:02X}".format(*c)

def _draw_rect(pdf, x, y, w, h, fill=None, stroke=None):
    """Draw a filled/stroked rectangle."""
    style = ""
    if fill:
        pdf.set_fill_color(*fill)
        style += "F"
    if stroke:
        pdf.set_draw_color(*stroke)
        style += "D"
    if style:
        pdf.set_line_width(0.3)
        pdf.rect(x, y, w, h, style=style)


class AlphaPilotPDF(FPDF):
    """Professional Chinese brochure with web-style design"""

    def __init__(self):
        super().__init__()
        if Path(_CJK_FONT).exists():
            self.add_font("CN", "", _CJK_FONT)
            self._cn = True
        else:
            self._cn = False
        # Register a bold version (same file, fpdf2 will simulate)
        if self._cn:
            try:
                self.add_font("CN", "B", _CJK_FONT)
            except Exception:
                pass

    def f(self, style="", size=10):
        return ("CN", style or "", size) if self._cn else ("Helvetica", style or "", size)

    def header(self):
        if self.page_no() <= 2:
            return
        self.set_font(*self.f("", 7))
        self.set_text_color(*TEXT_MUT)
        self.cell(0, 5, "AlphaPilot  \u2014  全市场量化 alpha 框架", align="L")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font(*self.f("", 7))
        self.set_text_color(*TEXT_MUT)
        self.cell(0, 10, f"\u4fdd\u5bc6  |  Page {self.page_no()}/{{nb}}", align="C")

    # ── Section: Cover Page ──
    def cover(self):
        self.add_page()
        # Full dark bg
        self.set_fill_color(*BG_DARK)
        self.rect(0, 0, 210, 297, "F")

        # Top accent line
        self.set_fill_color(*BLUE)
        self.rect(0, 0, 210, 3, "F")

        # Decorative geometric elements
        self.set_draw_color(*BLUE)
        self.set_line_width(0.3)
        # Top right corner decoration
        pdf = self
        pdf.set_draw_color(*BLUE)
        pdf.set_line_width(0.5)
        pdf.line(170, 30, 190, 30)
        pdf.line(190, 30, 190, 50)
        pdf.set_line_width(0.2)
        pdf.line(160, 25, 195, 25)
        pdf.line(195, 25, 195, 60)

        # Brand logo
        if LOGO_PATH.exists():
            pdf.image(str(LOGO_PATH), x=30, y=55, w=60)

        # Title block
        pdf.set_y(100)
        pdf.set_font(*self.f("B", 32))
        pdf.set_text_color(*TEXT_PRI)
        pdf.cell(0, 14, "AlphaPilot", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(*self.f("", 13))
        pdf.set_text_color(*BLUE)
        pdf.cell(0, 8, "\u5168\u5e02\u573a\u91cf\u5316\u9009\u80a1\u6846\u67b6\u6982\u8ff0", align="C", new_x="LMARGIN", new_y="NEXT")

        # Divider
        pdf.ln(4)
        pdf.set_draw_color(*BLUE)
        pdf.set_line_width(0.6)
        pdf.line(60, pdf.get_y(), 150, pdf.get_y())
        pdf.ln(8)

        # Tagline
        pdf.set_font(*self.f("", 10))
        pdf.set_text_color(*TEXT_SEC)
        pdf.cell(0, 7, "\u591a\u6e90\u6570\u636e\u878d\u5408  |  \u53cc\u8f68\u8bc4\u5206\u5f15\u64ce  |  \u7ea7\u8054\u98ce\u63a7\u95e8\u67b6\u6784", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 7, "\u5168\u5e02\u573a\u8986\u76d6  |  \u76d8\u4e2d\u5b9e\u65f6\u81ea\u9002\u5e94  |  \u96f6\u4ed8\u8d39\u6570\u636e\u4f9d\u8d56", align="C", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(25)

        # Bottom info bar
        pdf.set_fill_color(*BG_CARD)
        pdf.rect(20, 250, 170, 30, "F")
        pdf.set_draw_color(*BORDER)
        pdf.rect(20, 250, 170, 30, "D")
        pdf.set_font(*self.f("", 8))
        pdf.set_text_color(*TEXT_MUT)
        pdf.set_xy(25, 255)
        pdf.cell(160, 5, "\u4ea7\u54c1\u8425\u9500\u7b80\u4ecb  |  \u4ec5\u5305\u542b\u6846\u67b6\u5c42\u5185\u5bb9\uff0c\u4e0d\u6d89\u53ca\u6838\u5fc3\u7b97\u6cd5\u7ec6\u8282", align="C")
        pdf.set_xy(25, 262)
        pdf.cell(160, 5, f"AlphaPilot v3  |  {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}", align="C")

    # ── Section helpers ──
    def section_title(self, num, title):
        self.set_font(*self.f("B", 17))
        self.set_text_color(*TEXT_PRI)
        label = f"{num}. {title}" if num else title
        self.cell(0, 10, label, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*BLUE)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.l_margin + 35, self.get_y())
        self.ln(7)

    def body(self, text):
        self.set_font(*self.f("", 9.5))
        self.set_text_color(*TEXT_SEC)
        self.multi_cell(0, 5.5, text)
        self.ln(3)

    def bullet(self, bold_part, rest):
        self.set_x(self.l_margin + 3)
        self.set_font(*self.f("", 9.5))
        self.set_text_color(*TEXT_SEC)
        w = self.w - self.l_margin - self.r_margin - 3
        self.multi_cell(w, 5.5, f"  \u2022  {bold_part}{rest}")
        self.ln(0.5)

    def card(self, title, content):
        """Dark card with title bar"""
        x, y = self.l_margin, self.get_y()
        cw = self.w - self.l_margin - self.r_margin
        # Pre-calc height
        self.set_font(*self.f("", 9))
        lines = len(self.multi_cell(cw - 8, 5, content, dry_run=True, output="LINES"))
        ch = 6 + 4 + lines * 5 + 6

        # Check page break
        if y + ch > self.h - 25:
            self.add_page()
            y = self.get_y()

        # Card bg
        _draw_rect(self, x, y, cw, ch, fill=BG_CARD, stroke=BORDER)

        # Title bar
        self.set_fill_color(*BLUE)
        self.rect(x + 1, y + 1, cw - 2, 6, "F")
        self.set_font(*self.f("B", 9))
        self.set_text_color(*BLUE_DK)
        self.set_xy(x + 4, y + 1.5)
        self.cell(cw - 8, 4, title)

        # Content
        self.set_xy(x + 4, y + 8)
        self.set_font(*self.f("", 9))
        self.set_text_color(*TEXT_SEC)
        self.multi_cell(cw - 8, 5, content)
        self.set_y(y + ch + 4)

    def kpi_box(self, label, value, color):
        """Small KPI indicator"""
        x = self.get_x()
        y = self.get_y()
        bw = 40
        _draw_rect(self, x, y, bw, 18, fill=BG_CARD, stroke=BORDER)
        self.set_font(*self.f("", 8))
        self.set_text_color(*TEXT_MUT)
        self.set_xy(x, y + 2)
        self.cell(bw, 5, label, align="C")
        self.set_font(*self.f("B", 11))
        self.set_text_color(*color)
        self.set_xy(x, y + 8)
        self.cell(bw, 8, value, align="C")

    # ── Flowchart: Pipeline ──
    def draw_pipeline_flow(self):
        """Draw the full pipeline flowchart"""
        y0 = self.get_y() + 4
        cx = self.w / 2  # center x
        
        x_start = self.l_margin + 5
        x_end = self.w - self.r_margin - 5
        total_w = x_end - x_start
        
        steps = [
            ("全市场\n5000+ 只 A 股", BG_DARK),
            ("因子计算\n130+ 因子", BG_CARD2),
            ("ICIR 加权\n质量评分", BG_CARD2),
            ("门控链\n7 层过滤", BG_CARD2),
            ("09:35 动量扫描\n双轨融合", BG_CARD2),
            ("Top37\n推荐池", BG_CARD2),
            ("模拟盘\n执行", BG_CARD2),
        ]
        
        n = len(steps)
        box_w = min(28, (total_w - (n-1)*6) / n)
        gap = (total_w - n * box_w) / (n - 1)
        
        # Title
        self.set_font(*self.f("B", 10))
        self.set_text_color(*GREEN)
        self.cell(0, 6, "\u7cbe\u9009\u6f0f\u6597\u6d41\u7a0b\u56fe", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        
        for i, (label, color) in enumerate(steps):
            x = x_start + i * (box_w + gap)
            y = y0
            
            # Box
            _draw_rect(self, x, y, box_w, 22, fill=color, stroke=BLUE if i == len(steps)-1 else BORDER)
            
            # Highlight the final steps
            if i >= 4:
                self.set_draw_color(*BLUE)
                self.set_line_width(0.3)
                self.rect(x, y, box_w, 22, style="D")
            
            # Label
            self.set_font(*self.f("", 6.5))
            self.set_text_color(*TEXT_PRI if i >= 4 else TEXT_SEC)
            lines = label.split("\n")
            for j, line in enumerate(lines):
                lh = 22 / len(lines)
                self.set_xy(x, y + j * lh + (lh - 3) / 2)
                self.cell(box_w, 4, line, align="C")
            
            # Arrow between boxes
            if i < n - 1:
                ax = x + box_w
                ay = y + 11
                self.set_draw_color(*TEXT_MUT)
                self.set_line_width(0.4)
                self.line(ax + 1, ay, ax + gap - 1, ay)
                # Arrow head
                self.line(ax + gap - 4, ay - 2, ax + gap - 1, ay)
                self.line(ax + gap - 4, ay + 2, ax + gap - 1, ay)
        
        self.set_y(y0 + 28)

    # ── Flowchart: Dual Track ──
    def draw_dual_track(self):
        """Draw dual-track scoring architecture"""
        y0 = self.get_y() + 3
        
        # Title
        self.set_font(*self.f("B", 10))
        self.set_text_color(*GREEN)
        self.cell(0, 6, "\u53cc\u8f68\u8bc4\u5206\u67b6\u6784\u56fe", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        
        cx = self.w / 2
        cw = 70
        
        # Track A (left)
        ax = self.l_margin + 5
        # Track A boxes
        a_steps = ["05:00 全市场因子计算", "ICIR 因子加权", "质量评分 (Quality Score)"]
        for i, s in enumerate(a_steps):
            y = y0 + i * 14
            # Box
            _draw_rect(self, ax, y, cw, 11, fill=BG_CARD, stroke=BORDER)
            # Label
            self.set_font(*self.f("", 7.5))
            self.set_text_color(*TEXT_PRI if i == 2 else TEXT_SEC)
            self.set_xy(ax, y + 2)
            self.cell(cw, 7, s, align="C")
            # Arrow down
            if i < 2:
                self.set_draw_color(*BLUE)
                self.set_line_width(0.3)
                self.line(ax + cw/2, y + 11, ax + cw/2, y + 14)
                self.line(ax + cw/2 - 2, y + 12.5, ax + cw/2, y + 14)
                self.line(ax + cw/2 + 2, y + 12.5, ax + cw/2, y + 14)
        
        # Track B (right)
        bx = self.w - self.r_margin - 5 - cw
        b_steps = ["09:35 全市场资金扫描", "akshare 实时资金流", "动量评分 (Momentum Score)"]
        for i, s in enumerate(b_steps):
            y = y0 + i * 14
            _draw_rect(self, bx, y, cw, 11, fill=BG_CARD, stroke=BORDER)
            self.set_font(*self.f("", 7.5))
            self.set_text_color(*TEXT_PRI if i == 2 else TEXT_SEC)
            self.set_xy(bx, y + 2)
            self.cell(cw, 7, s, align="C")
            if i < 2:
                self.set_draw_color(*GOLD)
                self.set_line_width(0.3)
                self.line(bx + cw/2, y + 11, bx + cw/2, y + 14)
                self.line(bx + cw/2 - 2, y + 12.5, bx + cw/2, y + 14)
                self.line(bx + cw/2 + 2, y + 12.5, bx + cw/2, y + 14)
        
        # Fusion box (center, below)
        fy = y0 + 3 * 14 + 6
        fw = 90
        _draw_rect(self, cx - fw/2, fy, fw, 14, fill=BLUE_DK, stroke=BLUE)
        self.set_font(*self.f("B", 9))
        self.set_text_color(*BLUE_LT)
        self.set_xy(cx - fw/2, fy + 3)
        self.cell(fw, 8, "\u878d\u5408\u8bc4\u5206 = \u8d28\u91cf\u5206 x 50% + \u52a8\u91cf\u5206 x 50%", align="C")
        
        # Arrows from Track A & B to Fusion
        a_end_y = y0 + 2 * 14 + 11
        b_end_y = y0 + 2 * 14 + 11
        self.set_draw_color(*BLUE)
        self.set_line_width(0.3)
        # From A
        self.line(ax + cw/2, a_end_y, ax + cw/2, a_end_y + 6)
        self.line(ax + cw/2, a_end_y + 6, cx - fw/2, a_end_y + 6)
        self.line(cx - fw/2, a_end_y + 6, cx - fw/2, fy)
        # From B
        self.line(bx + cw/2, b_end_y, bx + cw/2, b_end_y + 6)
        self.line(bx + cw/2, b_end_y + 6, cx + fw/2, b_end_y + 6)
        self.line(cx + fw/2, b_end_y + 6, cx + fw/2, fy)
        
        # Arrow from fusion down
        ffy = fy + 14
        self.set_draw_color(*GREEN)
        self.set_line_width(0.4)
        self.line(cx, ffy, cx, ffy + 6)
        self.line(cx - 2, ffy + 4, cx, ffy + 6)
        self.line(cx + 2, ffy + 4, cx, ffy + 6)
        
        # Output
        oy = ffy + 8
        _draw_rect(self, cx - 25, oy, 50, 10, fill=GREEN, stroke=GREEN)
        self.set_font(*self.f("B", 8))
        self.set_text_color(*BG_DARK)
        self.set_xy(cx - 25, oy + 2)
        self.cell(50, 6, "\u7ec8\u6781\u6392\u540d Top37", align="C")
        
        self.set_y(oy + 16)

    # ── Flowchart: Gate Chain ──
    def draw_gate_chain(self):
        """Draw cascaded gate chain flowchart"""
        y0 = self.get_y() + 3
        
        self.set_font(*self.f("B", 10))
        self.set_text_color(*GREEN)
        self.cell(0, 6, "\u7ea7\u8054\u98ce\u63a7\u95e8\u94fe", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        
        x = self.l_margin + 5
        end_x = self.w - self.r_margin - 5
        total_w = end_x - x
        
        gates = [
            ("1", "\u4e0a\u5e02\u516c\u53f8\u95e8", "\u6dd8\u6c70 ST/-\u6d41\u52a8\u6027", BG_CARD2),
            ("2", "\u4e1a\u7ee9\u95e8", "\u6392\u9664\u4e1a\u7ee9\u5927\u8dcc", BG_CARD2),
            ("3", "\u8d44\u91d1\u95e8", "\u786c\u7b5b\u8d44\u91d1\u6d41\u5411", BG_CARD2),
            ("4", "\u677f\u5757\u95e8", "\u884c\u4e1a\u8f6e\u52a8\u8c03\u6574", BG_CARD2),
            ("5", "\u5206\u6563\u95e8", "\u540c\u677f\u5757\u4e0a\u9650", BG_CARD2),
            ("6", "\u73af\u5883\u95e8", "\u5e02\u573a\u6001\u52bf\u8c03\u8282", BG_CARD2),
        ]
        
        box_w = (total_w - (len(gates)-1)*3) / len(gates)
        box_h = 22
        
        for i, (num, name, desc, color) in enumerate(gates):
            gx = x + i * (box_w + 3)
            gy = y0
            
            _draw_rect(self, gx, gy, box_w, box_h, fill=color, stroke=BORDER)
            # Number badge
            self.set_fill_color(*BLUE)
            self.circle(gx + 5, gy + 5, 4)
            self.set_font(*self.f("B", 6))
            self.set_text_color(*TEXT_PRI)
            self.set_xy(gx + 2, gy + 2)
            self.cell(6, 6, num, align="C")
            
            # Name
            self.set_font(*self.f("B", 7))
            self.set_text_color(*TEXT_PRI)
            self.set_xy(gx + 10, gy + 1.5)
            self.cell(box_w - 10, 5, name)
            
            # Desc
            self.set_font(*self.f("", 6))
            self.set_text_color(*TEXT_SEC)
            self.set_xy(gx + 2, gy + 9)
            self.cell(box_w - 4, 10, desc, align="C")
            
            # Arrow
            if i < len(gates) - 1:
                ax = gx + box_w
                ay = gy + box_h/2
                self.set_draw_color(*TEXT_MUT)
                self.set_line_width(0.3)
                self.line(ax + 0.5, ay, ax + 2.5, ay)
                self.line(ax + 1.5, ay - 1.5, ax + 2.5, ay)
                self.line(ax + 1.5, ay + 1.5, ax + 2.5, ay)
        
        self.set_y(y0 + box_h + 8)

    # ── Timeline ──
    def draw_timeline(self):
        """Draw intraday timeline"""
        y0 = self.get_y() + 3
        self.set_font(*self.f("B", 10))
        self.set_text_color(*GREEN)
        self.cell(0, 6, "\u5168\u5929\u5019\u65f6\u95f4\u7ebf", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        
        events = [
            ("05:00", "\u5168\u7ba1\u7ebf\u6267\u884c", "\u56e0\u5b50\u8ba1\u7b97 \u2192 ICIR \u52a0\u6743 \u2192 \u591a\u95e8\u63a7\u8fc7\u6ee4 \u2192 \u8d28\u91cf\u8bc4\u5206", BLUE),
            ("09:35", "\u5168\u5e02\u573a\u626b\u63cf", "\u5b9e\u65f6\u8d44\u91d1\u6d41\u6570\u636e \u2192 \u52a8\u91cf\u8bc4\u5206 \u2192 \u53cc\u8f68\u878d\u5408 \u2192 \u7ec8\u6781\u6392\u540d", GOLD),
            ("10:00", "\u76d8\u4e2d\u5de1\u68c0 1", "\u677f\u5757\u8d44\u91d1\u6d41\u76d1\u6d4b\u2192\u6301\u4ed3\u677f\u5757\u53cd\u8f6c\u62a5\u8b66", GREEN),
            ("11:00", "\u76d8\u4e2d\u5de1\u68c0 2", "\u6301\u7eed\u76d1\u6d4b\u677f\u5757\u8d44\u91d1\u6d41\u53ca\u65e9\u8b66", GREEN),
            ("13:30", "\u76d8\u4e2d\u5de1\u68c0 3", "\u5348\u540e\u5f00\u76d8\u91cd\u65b0\u8bc4\u4f30\u6301\u4ed3\u98ce\u9669", GREEN),
            ("14:30", "\u6536\u76d8\u51b3\u7b56\u7a97", "\u786c\u6b62\u635f\u786e\u8ba4 / T+2/T+3\u5f3a\u5236\u5e73\u4ed3\u51b3\u7b56", RED),
        ]
        
        # Vertical line
        lx = self.l_margin + 20
        self.set_draw_color(*BLUE)
        self.set_line_width(0.3)
        self.line(lx, y0, lx, y0 + len(events) * 22)
        
        for i, (time, title, desc, color) in enumerate(events):
            ey = y0 + i * 22
            
            # Timeline dot
            dot_color = color
            self.set_fill_color(*dot_color)
            self.circle(lx, ey + 6, 3)
            
            # Time tag
            self.set_fill_color(*BG_CARD)
            _draw_rect(self, lx + 8, ey, 22, 12, fill=BG_CARD, stroke=BORDER)
            self.set_font(*self.f("B", 8))
            self.set_text_color(*color)
            self.set_xy(lx + 8, ey + 2)
            self.cell(22, 8, time, align="C")
            
            # Title
            self.set_font(*self.f("B", 9))
            self.set_text_color(*TEXT_PRI)
            self.set_xy(lx + 34, ey)
            self.cell(30, 5, title)
            
            # Description
            self.set_font(*self.f("", 7.5))
            self.set_text_color(*TEXT_SEC)
            self.set_xy(lx + 34, ey + 6)
            self.cell(self.w - lx - 34 - self.r_margin, 10, desc)
        
        self.set_y(y0 + len(events) * 22 + 6)


def build_pdf():
    pdf = AlphaPilotPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_left_margin(18)
    pdf.set_right_margin(18)

    # ═══════════ COVER ═══════════
    pdf.cover()

    # ═══════════ PAGE 2: Architecture Overview ═══════════
    pdf.add_page()
    pdf.set_fill_color(*BG_DARK)
    pdf.rect(0, 0, 210, 297, "F")

    pdf.section_title(1, "\u67b6\u6784\u603b\u89c8")
    pdf.body(
        "AlphaPilot \u662f\u4e00\u5957\u4e13\u4e3a A \u80a1\u5e02\u573a\u6253\u9020\u7684\u4e0b\u4e00\u4ee3\u91cf\u5316\u9009\u80a1\u6846\u67b6\u3002"
        "\u7cfb\u7edf\u901a\u8fc7\u591a\u9636\u6bb5\u6f0f\u6597\u7ba1\u7ebf\uff0c\u6bcf\u5929\u5bf9 5000+ \u53ea\u5168\u90e8 A \u80a1\u8fdb\u884c\u7b5b\u9009\u3001"
        "\u8bc4\u5206\u3001\u8fc7\u6ee4\u548c\u6392\u540d\u2014\u2014\u7ed3\u5408\u4e86\u4f20\u7edf\u56e0\u5b50\u8bc4\u5206\u4e0e\u5b9e\u65f6\u5e02\u573a\u5fae\u89c2\u7ed3\u6784\u4fe1\u53f7\u3002"
    )

    # KPI row
    pdf.ln(2)
    x0 = pdf.l_margin
    pdf.set_x(x0)
    pdf.kpi_box("A\u80a1\u8986\u76d6", "5,000+", BLUE)
    pdf.set_x(x0 + 45)
    pdf.kpi_box("\u56e0\u5b50\u5e93", "130+", GOLD)
    pdf.set_x(x0 + 90)
    pdf.kpi_box("\u95e8\u63a7\u5c42", "7\u7ea7", GREEN)
    pdf.set_x(x0 + 135)
    pdf.kpi_box("\u6570\u636e\u6210\u672c", "\u514d\u8d39", PURPLE)
    pdf.ln(24)

    # Design philosophy cards
    pdf.card("\u8bbe\u8ba1\u54f2\u5b66\u4e00\u89c8",
        "\u5206\u5c42\u7ba1\u7ebf\uff1a\u6bcf\u4e00\u9636\u6bb5\u90fd\u662f\u4e00\u5c42\u8d28\u91cf\u63a7\u5236\u2014\u2014\u4ece\u56e0\u5b50\u8bc4\u5206\u5230\u677f\u5757\u8f6e\u52a8\u518d\u5230\u76d8\u4e2d\u52a8\u91cf\uff0c\u786e\u4fdd\u53ea\u6709\u6700\u9ad8\u4fe1\u5fc3\u5ea6\u7684\u5019\u9009\u80fd\u5b58\u6d3b\u5230\u6267\u884c\u3002\n\n"
        "\u65e0\u5355\u70b9\u6545\u969c\uff1a\u67b6\u6784\u5929\u751f\u6a21\u5757\u5316\u3002\u67d0\u4e00\u6570\u636e\u6e90\u6216\u6a21\u578b\u5931\u6548\u65f6\uff0c\u5176\u4f59\u5c42\u4ecd\u53ef\u72ec\u7acb\u8fd0\u4f5c\u3002\n\n"
        "\u76d8\u4e2d\u81ea\u9002\u5e94\uff1a\u4e0e\u4f20\u7edf\u6536\u76d8\u4ef7\u6a21\u578b\u4e0d\u540c\uff0cAlphaPilot \u5728\u76d8\u4e2d\u4f7f\u7528\u5b9e\u65f6\u8d44\u91d1\u6d41\u3001\u4ef7\u683c\u52a8\u4f5c\u548c\u677f\u5757\u7ea7\u8d44\u672c\u8fd0\u52a8\u6570\u636e\u6765\u5237\u65b0\u89c2\u70b9\u3002"
    )

    # Pipeline flowchart
    pdf.ln(2)
    pdf.draw_pipeline_flow()

    # ═══════════ Multi-Source Data ═══════════
    pdf.section_title(2, "\u591a\u6e90\u6570\u636e\u878d\u5408")
    pdf.body(
        "AlphaPilot \u4f4d\u4e8e\u4e09\u5927\u6570\u636e\u57df\u7684\u4ea4\u53c9\u70b9\uff0c\u6bcf\u4e2a\u57df\u8d21\u732e\u72ec\u7279\u7684\u4fe1\u53f7\u7ef4\u5ea6\uff1a"
    )
    pdf.bullet("\u57fa\u672c\u9762\u4e0e\u56e0\u5b50\u6570\u636e  ",
        "\u2014 130+ \u9879\u6280\u672f\u3001\u57fa\u672c\u9762\u548c\u66ff\u4ee3\u56e0\u5b50\uff0c\u6bcf\u65e5\u4ece\u6536\u76d8\u4ef7\u6570\u636e\u3001\u5b63\u5ea6\u8d22\u62a5\u3001\u4e1a\u7ee9\u9884\u544a\u4e2d\u8ba1\u7b97\u3002\u56e0\u5b50\u6743\u91cd\u901a\u8fc7 ICIR\uff08\u4fe1\u606f\u7cfb\u6570\u4e0e\u4fe1\u606f\u6bd4\u7684\u6bd4\u503c\uff09\u4f18\u5316\uff0c\u786e\u4fdd\u53ea\u6709\u6301\u7eed\u6709\u9884\u6d4b\u529b\u7684\u4fe1\u53f7\u9a71\u52a8\u6700\u7ec8\u8bc4\u5206\u3002")
    pdf.bullet("\u5b9e\u65f6\u5e02\u573a\u5fae\u89c2\u7ed3\u6784  ",
        "\u2014 60\u79d2\u5237\u65b0\u7684\u5168\u5e02\u573a\u8d44\u91d1\u6d41\u6570\u636e\uff0c\u8986\u76d6\u673a\u6784\u51c0\u6d41\u3001\u4e3b\u52a8\u4e70\u5165\u6bd4\u3001\u6362\u624b\u7387\u3001\u91cf\u6bd4\u7b49\u6838\u5fc3\u4fe1\u53f7\u3002\u5168\u90e8\u6765\u6e90\u4e8e\u514d\u8d39\u516c\u5171\u63a5\u53e3\uff0c\u65e0\u9700\u6602\u8d35\u7684\u6570\u636e\u7ec8\u7aef\u8ba2\u9605\u3002")
    pdf.bullet("\u677f\u5757\u4e0e\u884c\u4e1a\u8d44\u91d1\u6d41  ",
        "\u2014 \u5168\u5929\u8ddf\u8e2a\u884c\u4e1a\u7ea7\u8d44\u672c\u8fd0\u52a8\uff0c\u63d0\u4f9b\u677f\u5757\u8f6e\u52a8\u9884\u8b66\u3002\u6839\u636e\u96c6\u5408\u673a\u6784\u6d41\u91cf\u6a21\u5f0f\u5c06\u677f\u5757\u5212\u5206\u4e3a\u300c\u504f\u597d\u300d\u3001\u300c\u907f\u5f00\u300d\u3001\u300c\u89c2\u5bdf\u300d\u4e09\u4e2a\u6863\u4f4d\u3002")

    # ═══════════ Dual-Track Scoring ═══════════
    pdf.add_page()
    pdf.set_fill_color(*BG_DARK)
    pdf.rect(0, 0, 210, 297, "F")

    pdf.section_title(3, "\u53cc\u8f68\u8bc4\u5206\u5f15\u64ce")
    pdf.body(
        "\u8bc4\u5206\u5f15\u64ce\u878d\u5408\u4e86\u4e24\u6761\u72ec\u7acb\u7684\u8bc4\u4f30\u8f68\u9053\uff0c\u6bcf\u6761\u8d21\u732e\u4e00\u4e2a\u72ec\u7279\u7684\u80a1\u7968\u8d28\u91cf\u7ef4\u5ea6\uff1a"
    )

    pdf.card("Track A \u2014 \u8d28\u91cf\u8bc4\u5206 (ICIR \u56e0\u5b50\u52a0\u6743)",
        "\u591a\u56e0\u5b50 alpha \u6a21\u578b\uff0c\u4f7f\u7528 Cross-sectional z-score \u5bf9\u6bcf\u53ea\u80a1\u7968\u8bc4\u5206\u3002"
        "\u56e0\u5b50\u6743\u91cd\u901a\u8fc7 ICIR\uff08\u4fe1\u606f\u7cfb\u6570\u7684\u5747\u503c\u9664\u4ee5\u6807\u51c6\u5dee\uff09\u4f18\u5316\uff0c\u8fd9\u662f\u884c\u4e1a\u6807\u51c6\u7684\u56e0\u5b50\u4e00\u81f4\u6027\u5ea6\u91cf\u6307\u6807\u3002"
        "\u7ed3\u679c\u662f\u4e00\u4e2a\u7a33\u5b9a\u3001\u4f4e\u6362\u624b\u7684\u8d28\u91cf\u6392\u540d\uff0c\u8bc6\u522b\u5177\u6709\u826f\u597d\u98ce\u9669\u8c03\u6574\u7279\u5f81\u7684\u80a1\u7968\u3002")

    pdf.card("Track B \u2014 \u52a8\u91cf\u8bc4\u5206 (\u5b9e\u65f6\u8d44\u91d1\u6d41)",
        "\u5b9e\u65f6\u8bc4\u5206\u5f15\u64ce\uff0c\u5728 09:35 \u6267\u884c\u5168\u5e02\u573a\u626b\u63cf\u3002\u8bc4\u4f30\u6bcf\u53ea\u80a1\u7968\u7684\u5b9e\u65f6\u8d44\u91d1\u52a8\u6001\uff1a"
        "\u673a\u6784\u51c0\u6d41\u3001\u4e3b\u52a8\u4e70\u5165\u538b\u529b\u3001\u6362\u624b\u653e\u91cf\u3001\u4ef7\u683c\u52a8\u91cf\u3002"
        "\u80fd\u6355\u6349\u5230\u7a81\u7136\u8d44\u91d1\u6d8c\u5165\u4f46\u666e\u901a\u56e0\u5b50\u6a21\u578b\u5b8c\u5168\u9519\u8fc7\u7684\u80a1\u7968\u3002")

    pdf.ln(2)
    # Draw Dual Track chart
    pdf.draw_dual_track()

    # ═══════════ Gate Chain ═══════════
    pdf.section_title(4, "\u7ea7\u8054\u98ce\u63a7\u95e8\u6846\u67b6")
    pdf.body(
        "\u5728\u8bc4\u5206\u548c\u6267\u884c\u4e4b\u95f4\uff0c\u6bcf\u4e2a\u5019\u9009\u80a1\u7984\u7ecf\u8fc7\u4e00\u7cfb\u5217\u98ce\u63a7\u95e8\u3002"
        "\u6bcf\u9053\u95e8\u8bc4\u4f30\u7279\u5b9a\u7684\u98ce\u9669\u7ef4\u5ea6\uff0c\u53ef\u4ee5\u76f4\u63a5\u6dd8\u6c70\u5019\u9009\u6216\u8c03\u6574\u5176\u8bc4\u5206\uff1a"
    )

    pdf.draw_gate_chain()

    pdf.bullet("\u4e0a\u5e02\u516c\u53f8\u95e8  ",
        "\u2014 \u6dd8\u6c70\u6d41\u52a8\u6027\u4e0d\u8db3\u3001ST \u6807\u8bb0\u3001\u9000\u5e02\u98ce\u9669\u80a1\u7968\u3002\u786e\u4fdd\u4ea4\u6613\u5b87\u5b99\u7684\u6e05\u6d01\u3002")
    pdf.bullet("\u4e1a\u7ee9\u95e8  ",
        "\u2014 \u6392\u9664\u51c0\u5229\u6da6\u540c\u6bd4\u5927\u5e45\u4e0b\u964d\u7684\u80a1\u7968\uff0c\u907f\u514d\u4ef7\u503c\u9677\u9631\u3002")
    pdf.bullet("\u8d44\u91d1\u95e8  ",
        "\u2014 \u786c\u7b5b\u8d44\u91d1\u6d41\u9762\u4e34\u5229\u7a7a\u7684\u80a1\u7968\uff0c\u786e\u4fdd\u6240\u9009\u80a1\u7968\u6709\u771f\u5b9e\u7684\u673a\u6784\u4e70\u5165\u5174\u8da3\u3002")
    pdf.bullet("\u677f\u5757\u95e8  ",
        "\u2014 \u6839\u636e\u677f\u5757\u7ea7\u8d44\u672c\u8f6e\u52a8\u52a8\u6001\u8c03\u6574\u8bc4\u5206\uff0c\u907f\u5f00\u673a\u6784\u6b63\u5728\u51fa\u8d27\u7684\u884c\u4e1a\u3002")
    pdf.bullet("\u5206\u6563\u95e8  ",
        "\u2014 \u9650\u5236\u96c6\u4e2d\u5ea6\u98ce\u9669\uff1aTop10 \u540c\u677f\u5757\u6700\u591a 2 \u53ea\uff0c\u5168\u6c60\u6700\u591a 4 \u53ea\u3002")
    pdf.bullet("\u73af\u5883\u95e8  ",
        "\u2014 \u6839\u636e\u5e7f\u4e49\u5e02\u573a\u6001\u52bf\u8c03\u6574\u4ed3\u4f4d\u5927\u5c0f\u2014\u2014\u725b\u5e02\u3001\u632f\u8361\u3001\u9632\u5fa1\u6a21\u5f0f\u3002")
    pdf.bullet("\u76d8\u4e2d\u5de1\u68c0  ",
        "\u2014 \u6301\u7eed\u76d1\u6d4b\u6301\u4ed3\u80a1\u7968\u7684\u677f\u5757\u8d44\u91d1\u53cd\u8f6c\uff0c\u4ece\u6d41\u5165\u8f6c\u4e3a\u6d41\u51fa\u65f6\u89e6\u53d1\u81ea\u52a8\u79bb\u573a\u3002")

    # ═══════════ Intraday Timeline ═══════════
    pdf.add_page()
    pdf.set_fill_color(*BG_DARK)
    pdf.rect(0, 0, 210, 297, "F")

    pdf.section_title(5, "\u76d8\u4e2d\u81ea\u9002\u5e94\u7ba1\u7ebf")
    pdf.body(
        "AlphaPilot \u7684\u7ade\u4e89\u4f18\u52bf\u5728\u4e8e\u5176\u76d8\u4e2d\u5237\u65b0\u80fd\u529b\u3002\u7cfb\u7edf\u4e0d\u4f9d\u8d56\u5355\u4e00\u7684\u5f00\u76d8\u524d\u6392\u540d\u2014\u2014"
        "\u5b83\u968f\u5e02\u573a\u7684\u8282\u594f\u8fdb\u5316\uff1a"
    )

    pdf.draw_timeline()

    pdf.body(
        "\u8fd9\u4e2a\u76d8\u4e2d\u5faa\u73af\u662f AlphaPilot \u4e0e\u4f20\u7edf\u6536\u76d8\u4ef7\u6a21\u578b\u7684\u672c\u8d28\u533a\u522b\u3002"
        "\u5f53\u4f20\u7edf\u7cfb\u7edf\u5728\u4e0b\u4e00\u4e2a\u6536\u76d8\u4ef7\u524d\u59cb\u7ec8\u4f7f\u7528\u6628\u5929\u7684\u6570\u636e\u4ea4\u6613\u65f6\uff0cAlphaPilot \u5728\u5f00\u76d8\u540e\u51e0\u5206\u949f\u5185\u5c31\u5b8c\u6210\u4e86\u81ea\u9002\u5e94\u3002"
    )

    # ═══════════ Risk Management ═══════════
    pdf.section_title(6, "\u98ce\u63a7\u4e0e\u4ed3\u4f4d\u7ba1\u7406")
    pdf.body(
        "AlphaPilot \u7684\u98ce\u63a7\u6846\u67b6\u5728\u4e09\u4e2a\u5c42\u7ea7\u540c\u65f6\u8fd0\u4f5c\uff1a"
    )
    pdf.bullet("\u7ec4\u5408\u5c42  ",
        "\u2014 \u6839\u636e\u5e02\u573a\u6001\u52bf\u52a8\u6001\u8c03\u6574\u4ed3\u4f4d\u66dd\u5149\u3002\u9ad8\u6ce2\u52a8\u671f\u95f4\u5207\u6362\u5230\u9632\u5fa1\u6a21\u5f0f\uff0c\u8d8b\u52bf\u5e02\u573a\u4e2d\u4fdd\u6301\u4e2d\u6027\u3002")
    pdf.bullet("\u6301\u4ed3\u5c42  ",
        "\u2014 \u52a8\u6001\u6b62\u76c8\u203b\u786c\u6b62\u635f\u203b\u65f6\u95f4\u5f3a\u5236\u5e73\u4ed3\uff08T+2/T+3\uff09\u4e09\u91cd\u4fdd\u62a4\u673a\u5236\u3002")
    pdf.bullet("\u677f\u5757\u5c42  ",
        "\u2014 \u677f\u5757\u96c6\u4e2d\u5ea6\u9650\u5236\u9632\u6b62\u8fc7\u5ea6\u66dd\u9732\u4e8e\u5355\u4e00\u884c\u4e1a\u3002\u76d8\u4e2d\u8d44\u91d1\u53cd\u8f6c\u68c0\u6d4b\u63d0\u4f9b\u989d\u5916\u9884\u8b66\u3002")

    # ═══════════ Key Advantages ═══════════
    pdf.add_page()
    pdf.set_fill_color(*BG_DARK)
    pdf.rect(0, 0, 210, 297, "F")
    pdf.section_title(None, "\u6838\u5fc3\u4f18\u52bf")

    advantages = [
        ("\u5168\u5e02\u573a\u8986\u76d6",
         "\u6bcf\u5929\u626b\u63cf 5,000+ \u53ea A \u80a1\uff0c\u65e0\u4efb\u610f\u89c4\u6a21\u6216\u6d41\u52a8\u6027\u7b5b\u5b50\uff0c\u4e0d\u9519\u8fc7\u4efb\u4f55\u6f5c\u5728\u673a\u4f1a\u3002",
         BLUE),
        ("\u96f6\u4ed8\u8d39\u6570\u636e\u4f9d\u8d56",
         "\u6240\u6709\u4e3b\u8981\u6570\u636e\u6e90\u5747\u6765\u81ea\u514d\u8d39\u516c\u5171 API\uff0c\u65e0\u9700\u6602\u8d35\u7684 Wind/\u5b8f\u6e90\u7b49\u6570\u636e\u7ec8\u7aef\u8ba2\u9605\u3002",
         GREEN),
        ("\u76d8\u4e2d\u81ea\u9002\u5e94\u80fd\u529b",
         "09:35 \u5168\u5e02\u573a\u5237\u65b0\uff0c\u4fdd\u8bc1\u7cfb\u7edf\u4ece\u4e0d\u4f7f\u7528\u8fc7\u671f\u7684\u9694\u591c\u6392\u540d\u4ea4\u6613\u3002\u8fd9\u5355\u72ec\u6d88\u9664\u4e86\u4e00\u4e2a\u4e3b\u8981\u7684 alpha \u8870\u51cf\u6e90\u3002",
         GOLD),
        ("\u6a21\u5757\u5316\u67b6\u6784",
         "\u6bcf\u4e2a\u7ba1\u7ebf\u9636\u6bb5\u90fd\u53ef\u72ec\u7acb\u66ff\u6362\u3002\u65b0\u7684\u6570\u636e\u6e90\u6216\u56e0\u5b50\u53ef\u63d2\u5165\u800c\u4e0d\u5f71\u54cd\u5176\u4f59\u7cfb\u7edf\u3002",
         PURPLE),
        ("\u677f\u5757\u611f\u77e5\u80fd\u529b",
         "\u884c\u4e1a\u7ea7\u8d44\u91d1\u6d41\u8ddf\u8e2a\u63d0\u4f9b\u5b8f\u89c2\u89c6\u89d2\uff0c\u9632\u6b62\u4e70\u5165\u673a\u6784\u6b63\u5728\u9ed8\u9ed8\u79bb\u573a\u7684\u677f\u5757\u3002",
         BLUE),
        ("\u5185\u5efa\u62a4\u680f",
         "\u4ece\u4e1a\u7ee9\u7b5b\u9009\u5230\u677f\u5757\u96c6\u4e2d\u5ea6\u9650\u5236\u518d\u5230\u76d8\u4e2d\u53cd\u8f6c\u68c0\u6d4b\uff0c\u98ce\u63a7\u63aa\u65bd\u5d4c\u5165\u6bcf\u4e2a\u9636\u6bb5\uff0c\u800c\u975e\u6700\u540e\u7c98\u8d34\u3002",
         GREEN),
    ]
    for title, desc, color in advantages:
        pdf.card(title, desc)

    # ═══════════ Save ═══════════
    pdf.output(str(OUT))
    print(f"PDF saved: {OUT} ({os.path.getsize(OUT) / 1024:.1f} KB)")
    return OUT


if __name__ == "__main__":
    build_pdf()
