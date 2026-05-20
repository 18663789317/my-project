# -*- coding: utf-8 -*-
"""生成保证金计算功能开发方案 PDF 报告"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# ── 注册中文字体 ──
FONT_PATH = "C:/Windows/Fonts"
pdfmetrics.registerFont(TTFont("SimHei", os.path.join(FONT_PATH, "simhei.ttf")))
pdfmetrics.registerFont(TTFont("Deng", os.path.join(FONT_PATH, "Deng.ttf")))
pdfmetrics.registerFont(TTFont("DengBold", os.path.join(FONT_PATH, "Dengb.ttf")))
pdfmetrics.registerFont(TTFont("DengLight", os.path.join(FONT_PATH, "Dengl.ttf")))

# ── 颜色定义 ──
C_PRIMARY = HexColor("#1a3a5c")
C_ACCENT = HexColor("#2980b9")
C_LIGHT_BG = HexColor("#f0f4f8")
C_BORDER = HexColor("#bcd4e6")
C_TEXT = HexColor("#2c3e50")
C_WARN = HexColor("#e67e22")
C_OK = HexColor("#27ae60")
C_HEADER_BG = HexColor("#1a3a5c")
C_ROW_ALT = HexColor("#f7f9fb")

# ── 样式 ──
styles = getSampleStyleSheet()

s_title = ParagraphStyle(
    "CTitle", fontName="SimHei", fontSize=22, leading=30,
    textColor=C_PRIMARY, alignment=TA_CENTER, spaceAfter=6*mm,
)
s_subtitle = ParagraphStyle(
    "CSubtitle", fontName="Deng", fontSize=11, leading=16,
    textColor=HexColor("#7f8c8d"), alignment=TA_CENTER, spaceAfter=10*mm,
)
s_h1 = ParagraphStyle(
    "CH1", fontName="SimHei", fontSize=16, leading=22,
    textColor=C_PRIMARY, spaceBefore=8*mm, spaceAfter=4*mm,
    borderWidth=0, borderPadding=0,
)
s_h2 = ParagraphStyle(
    "CH2", fontName="DengBold", fontSize=13, leading=18,
    textColor=C_ACCENT, spaceBefore=5*mm, spaceAfter=3*mm,
)
s_h3 = ParagraphStyle(
    "CH3", fontName="DengBold", fontSize=11, leading=15,
    textColor=C_PRIMARY, spaceBefore=3*mm, spaceAfter=2*mm,
)
s_body = ParagraphStyle(
    "CBody", fontName="Deng", fontSize=9.5, leading=15,
    textColor=C_TEXT, alignment=TA_JUSTIFY, spaceAfter=2*mm,
)
s_body_indent = ParagraphStyle(
    "CBodyIndent", parent=s_body, leftIndent=8*mm,
)
s_bullet = ParagraphStyle(
    "CBullet", fontName="Deng", fontSize=9.5, leading=15,
    textColor=C_TEXT, leftIndent=6*mm, bulletIndent=0,
    spaceAfter=1.5*mm,
)
s_code = ParagraphStyle(
    "CCode", fontName="Courier", fontSize=8, leading=12,
    textColor=HexColor("#333333"), backColor=C_LIGHT_BG,
    leftIndent=6*mm, spaceAfter=2*mm, borderWidth=0.5,
    borderColor=C_BORDER, borderPadding=4,
)
s_warn = ParagraphStyle(
    "CWarn", fontName="DengBold", fontSize=9.5, leading=15,
    textColor=C_WARN, leftIndent=6*mm, spaceAfter=2*mm,
)
s_ok = ParagraphStyle(
    "COK", fontName="DengBold", fontSize=9.5, leading=15,
    textColor=C_OK, leftIndent=6*mm, spaceAfter=2*mm,
)
s_table_header = ParagraphStyle(
    "CTH", fontName="SimHei", fontSize=8.5, leading=12,
    textColor=white, alignment=TA_CENTER,
)
s_table_cell = ParagraphStyle(
    "CTC", fontName="Deng", fontSize=8.5, leading=12,
    textColor=C_TEXT,
)
s_table_cell_c = ParagraphStyle(
    "CTCC", fontName="Deng", fontSize=8.5, leading=12,
    textColor=C_TEXT, alignment=TA_CENTER,
)
s_footer = ParagraphStyle(
    "CFooter", fontName="Deng", fontSize=7.5, leading=10,
    textColor=HexColor("#95a5a6"), alignment=TA_CENTER,
)
s_tag = ParagraphStyle(
    "CTag", fontName="DengBold", fontSize=8, leading=11,
    textColor=HexColor("#8e44ad"), leftIndent=4*mm,
)

# ── 工具函数 ──
def hr():
    return HRFlowable(width="100%", thickness=0.5, color=C_BORDER,
                       spaceBefore=3*mm, spaceAfter=3*mm)

def sp(n=3):
    return Spacer(1, n*mm)

def make_table(headers, rows, col_widths=None):
    """创建美观表格"""
    header_cells = [Paragraph(h, s_table_header) for h in headers]
    data = [header_cells]
    for row in rows:
        data.append([Paragraph(str(c), s_table_cell if i == 0 else s_table_cell_c)
                      for i, c in enumerate(row)])
    if col_widths is None:
        col_widths = [170*mm / len(headers)] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), C_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, C_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), C_ROW_ALT))
    t.setStyle(TableStyle(style_cmds))
    return t

def bullet(text):
    return Paragraph(f"• {text}", s_bullet)

def tag(text):
    return Paragraph(f"[{text}]", s_tag)


# ═══════════════════════════════════════════
#  报告正文
# ═══════════════════════════════════════════
def build_report(output_path):
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=18*mm, bottomMargin=18*mm,
        leftMargin=18*mm, rightMargin=18*mm,
    )
    story = []
    W = doc.width  # 可用宽度

    # ─── 封面 ───
    story.append(sp(30))
    story.append(Paragraph("保证金计算功能", s_title))
    story.append(Paragraph("开发方案 & 系统分析报告", s_title))
    story.append(sp(5))
    story.append(Paragraph("CH场外期权结构风险管理监控系统 V8.2", s_subtitle))
    story.append(hr())
    story.append(sp(3))
    cover_info = [
        ["报告类型", "技术方案评审 & 优化建议"],
        ["目标系统", "OTC-Risk-App (Streamlit + SQLite)"],
        ["源码规模", "app.py 95,096 行 / 单文件架构"],
        ["支持结构", "12 种期权结构类型"],
        ["报告日期", "2026-05-12"],
    ]
    cover_table = Table(
        [[Paragraph(r[0], s_table_header), Paragraph(r[1], s_table_cell)] for r in cover_info],
        colWidths=[40*mm, W - 40*mm],
    )
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), C_HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(cover_table)
    story.append(PageBreak())

    # ─── 目录 ───
    story.append(Paragraph("目 录", s_h1))
    story.append(hr())
    toc_items = [
        "第一部分  系统现状全面分析",
        "  1.1  系统架构概述",
        "  1.2  现有保证金体系分析",
        "  1.3  可复用的估值/定价函数清单",
        "  1.4  支持的结构类型与参数",
        "第二部分  Codex 计划书评审",
        "  2.1  计划书优点",
        "  2.2  计划书问题与不足",
        "第三部分  优化方案与建议",
        "  3.1  简化算法：用现有估值体系替代纯 SPAN",
        "  3.2  分结构类型的保证金计算策略",
        "  3.3  极简用户输入设计",
        "  3.4  统一保证金引擎优化设计",
        "  3.5  后台配置与数据存储",
        "  3.6  改进后的分阶段开发计划",
        "第四部分  详细技术方案",
        "  4.1  函数复用映射表",
        "  4.2  数据流设计",
        "  4.3  UI 接入方案",
        "  4.4  验收标准优化",
        "附录  关键代码位置索引",
    ]
    for item in toc_items:
        indent = 10*mm if item.startswith("  ") else 0
        fs = s_body if item.startswith("  ") else ParagraphStyle(
            "toc_h", fontName="DengBold", fontSize=10, leading=16,
            textColor=C_PRIMARY, spaceAfter=1*mm,
        )
        story.append(Paragraph(item.strip(), ParagraphStyle(
            "toc_item", parent=fs, leftIndent=indent,
        )))
    story.append(PageBreak())

    # ══════════════════════════════════════
    #  第一部分：系统现状
    # ══════════════════════════════════════
    story.append(Paragraph("第一部分  系统现状全面分析", s_h1))
    story.append(hr())

    # 1.1
    story.append(Paragraph("1.1  系统架构概述", s_h2))
    story.append(Paragraph(
        "本系统是一个面向场外期权（OTC Options）交易团队的一体化工作台，核心文件 app.py 共 95,096 行，"
        "采用 Streamlit Web 框架 + SQLite 数据库 + Pandas/NumPy 计算的单文件架构。"
        "系统涵盖结构管理、价格录入、现货/期权仓库、平仓回溯、监控计算、波动率分析、蒙卡回测等完整业务流程。", s_body))
    story.append(sp(2))

    story.append(Paragraph("系统模块分布：", s_h3))
    arch_data = [
        ["行号范围", "模块", "职责"],
        ["1-100", "Imports &amp; Logging", "标准库、第三方库导入；日志工具"],
        ["100-670", "全局常量与配置", "日期格式、路径、结构模板、保证金参数等"],
        ["673-1873", "DB 数据库层", "SQLite 连接管理、表结构定义、KV 存储"],
        ["1874-2510", "Trading Day", "中国日历集成、交易日判断与计算"],
        ["2511-22299", "Helpers 通用工具", "JSON解析、报价图渲染、平仓盈亏计算等"],
        ["22300-26745", "Strategy Registry", "StructureSpec、12种结构类型注册"],
        ["26746-30057", "Fetchers 数据读取", "从SQLite读取数据、Session缓存"],
        ["30058-51871", "Compute Engine", "台账计算、各结构日度状态机驱动"],
        ["51872-61252", "UI Helpers", "全局筛选器、页面横幅、字段渲染"],
        ["61253-80798", "Backtest &amp; MC", "胜率计算、蒙卡模拟、3D估值面、Greeks"],
        ["80799-95096", "UI 主界面", "10个页面的路由与渲染"],
    ]
    t = []
    for i, row in enumerate(arch_data):
        if i == 0:
            t.append([Paragraph(c, s_table_header) for c in row])
        else:
            t.append([Paragraph(c, s_table_cell_c) for c in row[:1]] +
                      [Paragraph(c, s_table_cell) for c in row[1:]])
    arch_table = Table(t, colWidths=[30*mm, 42*mm, W - 72*mm], repeatRows=1)
    arch_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ] + [("BACKGROUND", (0, i), (-1, i), C_ROW_ALT) for i in range(2, len(t), 2)]))
    story.append(arch_table)

    story.append(sp(3))
    story.append(Paragraph("共 10 个页面，通过侧边栏 radio 导航：", s_h3))
    pages_data = [
        ["页面", "行号", "说明"],
        ["生成策略组", "81425", "策略组主数据维护"],
        ["结构录入", "82032", "12种结构类型录入与编辑"],
        ["价格录入", "86254", "收价录入、akshare自动导入"],
        ["现货头寸仓库", "87095", "现货头寸管理、对冲匹配"],
        ["期权头寸仓库", "87943", "期权结构头寸总览、平仓"],
        ["监控计算", "92564", "核心监控：价格完整性、日度指标"],
        ["自助报价&amp;反解IV", "91981", "波动率工作室"],
        ["蒙卡系统", "92088", "概率分布、蒙卡模拟运算"],
        ["回测&amp;3D估值", "92430", "胜率回测、Greeks扫描"],
        ["精准套保", "92280", "累计结构精准套保优化"],
    ]
    story.append(make_table(
        pages_data[0], pages_data[1:],
        [38*mm, 22*mm, W - 60*mm],
    ))

    # 1.2
    story.append(Paragraph("1.2  现有保证金体系分析", s_h2))
    story.append(Paragraph(
        "当前系统的保证金计算采用「纯手工输入 + 比例换算」模式，"
        "用户手动输入保证金后，系统自动联动计算三个关联字段。"
        "系统中不存在任何 SPAN、VaR 等风险模型的自动计算逻辑。", s_body))
    story.append(sp(2))

    story.append(Paragraph("现有保证金字段（定义于 app.py 第276-285行）：", s_h3))
    margin_fields = [
        ["字段常量", "中文名称", "说明"],
        ["structure_initial_margin_wan", "结构初始保证金（万元）", "总保证金金额"],
        ["structure_margin_per_ton", "结构单吨保证金（元/吨）", "每吨保证金"],
        ["structure_margin_per_ton_rate_pct", "结构单吨保证金比例（%）", "占入场价百分比"],
        ["futures_margin_rate_pct", "期货单吨保证金比例（%）", "期货侧保证金率"],
    ]
    story.append(make_table(margin_fields[0], margin_fields[1:], [52*mm, 52*mm, W - 104*mm]))

    story.append(sp(3))
    story.append(Paragraph("现有保证金核心函数：", s_h3))
    func_data = [
        ["函数名", "行号", "功能"],
        ["structure_margin_wan_from_per_ton", "25941", "单吨保证金 → 万元"],
        ["structure_margin_per_ton_from_wan", "25949", "万元 → 单吨保证金"],
        ["structure_margin_per_ton_rate_pct", "25957", "单吨保证金 → 占比%"],
        ["structure_margin_per_ton_from_rate_pct", "25965", "占比% → 单吨保证金"],
        ["resolve_structure_margin_linked_values", "25980", "三字段联动核心函数"],
        ["normalize_structure_margin_payload", "26028", "多源别名兼容标准化"],
        ["structure_margin_reference_total_qty", "26133", "按策略类型计算参考总量"],
        ["merge_structure_margin_payload", "26100", "合并保证金到params"],
        ["compute_option_warehouse_margin_usage", "54981", "仓库级保证金占用"],
    ]
    story.append(make_table(func_data[0], func_data[1:], [62*mm, 18*mm, W - 80*mm]))

    story.append(sp(3))
    story.append(Paragraph("保证金数据流：", s_h3))
    story.append(Paragraph(
        "结构录入 UI → 4个 number_input → _sync_margin_values_from_source() "
        "→ resolve_structure_margin_linked_values() → normalize_structure_margin_payload() "
        "→ quote_payload (含 show_margin=True) → render_structure_quote_image() "
        "→ merge_structure_margin_payload() → 写入DB", s_code))

    story.append(sp(2))
    story.append(Paragraph("关键发现：", s_h3))
    story.append(bullet("当前保证金完全是「用户手工输入 + 比例换算」，无任何自动计算"))
    story.append(bullet("仓库级保证金采用简化算法：最大侧数量 × 均价 × 比例"))
    story.append(bullet("估值系统已预留保证金成本接口（第74108行注释），但尚未实现"))
    story.append(bullet("系统搜索 SPAN 仅匹配 colspan/span，无 SPAN 保证金模型"))

    # 1.3
    story.append(PageBreak())
    story.append(Paragraph("1.3  可复用的估值/定价函数清单", s_h2))
    story.append(Paragraph(
        "系统已拥有完整的期权估值基础设施，这是新保证金引擎最重要的资产。"
        "以下函数可直接或改造后用于保证金计算：", s_body))

    reuse_data = [
        ["函数", "行号", "保证金复用场景"],
        ["winrate_black76_vanilla_unit_price", "65323",
         "香草期权解析定价 — SPAN情景重估核心"],
        ["winrate_black76_vanilla_structure_value", "65352",
         "香草结构整体估值 — 含数量放大"],
        ["winrate_run_structure_valuation", "70094",
         "结构MC估值主入口 — 雪球/累计/气囊"],
        ["winrate_estimate_structure_path_values", "69740",
         "路径估值引擎 — 逐日状态机"],
        ["winrate_simulate_price_paths", "63857",
         "MC价格路径生成 — VaR场景基础"],
        ["winrate_simulate_bs_risk_neutral_price_paths", "69226",
         "风险中性MC路径 — 估值专用"],
        ["winrate_run_structure_greeks_scan", "74271",
         "Delta/Gamma/Vega/Theta — 灵敏度分析"],
        ["winrate_structure_greeks_scaled_snapshot", "73217",
         "按数量放大的Greeks"],
        ["winrate_black76_vanilla_implied_volatility", "65510",
         "IV反推 — 波动率冲击计算"],
        ["resolve_structure_margin_linked_values", "25980",
         "保证金联动 — 结果回填复用"],
        ["structure_margin_wan_from_per_ton", "25941",
         "单位换算 — 吨→万元"],
        ["detect_structure_termination_on_prices", "26665",
         "敲出检测 — 情景终止判断"],
    ]
    story.append(make_table(reuse_data[0], reuse_data[1:], [60*mm, 16*mm, W - 76*mm]))

    story.append(sp(3))
    story.append(Paragraph("重要常量：", s_h3))
    const_data = [
        ["常量", "行号", "值", "说明"],
        ["WINRATE_STRUCTURE_VALUATION_PATHS_DEFAULT", "64889", "10000", "MC默认路径数"],
        ["WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN", "64904", "BS_RISK_NEUTRAL", "风险中性模型"],
        ["VOLVAL_DEFAULT_RISK_FREE_RATE_PCT", "65788", "2.0", "默认无风险利率"],
    ]
    story.append(make_table(const_data[0], const_data[1:], [62*mm, 16*mm, 34*mm, W - 112*mm]))

    # 1.4
    story.append(sp(3))
    story.append(Paragraph("1.4  支持的结构类型与参数", s_h2))
    struct_data = [
        ["序号", "代码", "中文名", "大类", "必填参数"],
        ["1", "BASIC_RANGE", "普通累计", "累计",
         "入场价,行权价,敲出价"],
        ["2", "NO_KO", "无敲出累计", "累计",
         "入场价,行权价,倍数"],
        ["3", "FLOAT_KO", "浮动熔断累计", "累计",
         "入场价,行权价,敲出价,熔断行权价,倍数"],
        ["4", "FIXED_SUBSIDY", "固赔熔断累计", "累计",
         "入场价,行权价,障碍价,倍数,补贴"],
        ["5", "PREMIUM_SUBSIDY", "溢价累计", "累计",
         "入场价,行权价,倍数,补贴"],
        ["6", "RANGE_SUBSIDY", "区间补贴累计", "累计",
         "入场价,行权价,障碍价,倍数,补贴"],
        ["7", "PHOENIX_ACC_CALL", "凤凰累计(累购)", "凤凰",
         "入场价,敲入价,敲入行权价,敲出价,倍数,补贴"],
        ["8", "PHOENIX_ACC_PUT", "凤凰累计(累沽)", "凤凰",
         "同上"],
        ["9", "SAFETY_AIRBAG", "安全气囊", "气囊",
         "入场价,行权价,障碍价,倍数"],
        ["10", "SNOWBALL", "雪球结构", "雪球",
         "入场价 + params_json扩展参数"],
        ["11", "TRS", "TRS头寸", "TRS",
         "入场价"],
        ["12", "VANILLA_OPTION", "香草期权", "香草",
         "入场价,行权价,期权费"],
    ]
    story.append(make_table(struct_data[0], struct_data[1:],
                            [10*mm, 30*mm, 28*mm, 14*mm, W - 82*mm]))

    story.append(PageBreak())

    # ══════════════════════════════════════
    #  第二部分：Codex 计划书评审
    # ══════════════════════════════════════
    story.append(Paragraph("第二部分  Codex 计划书评审", s_h1))
    story.append(hr())

    # 2.1
    story.append(Paragraph("2.1  计划书优点", s_h2))
    story.append(bullet("目标清晰：从手工录入升级为「自动建议 + 可覆盖」模式，符合渐进式改造原则"))
    story.append(bullet("分阶段策略合理：先 SPAN-like 后 VaR，降低首期风险"))
    story.append(bullet("最少新增录入项理念正确：高级参数放后台配置，不增加一线人员负担"))
    story.append(bullet("验收标准具体可测：数量翻倍保证金翻倍、卖出＞买入等直觉校验"))
    story.append(bullet("第三阶段资金成本进报价有实际业务价值"))

    # 2.2
    story.append(Paragraph("2.2  计划书问题与不足", s_h2))

    story.append(Paragraph("问题一：未识别现有估值基础设施", s_h3))
    story.append(Paragraph(
        "计划书将 SPAN-like 设计为「从零构建」，包括构造压力情景、每情景重新估值等。"
        "但实际上系统已有完整的估值体系：", s_body))
    story.append(bullet("Black-76 解析定价（香草）—— app.py 第65323行"))
    story.append(bullet("MC路径模拟 + 逐日状态机估值（雪球/累计/气囊）—— 第70094行"))
    story.append(bullet("Greeks有限差分扫描（Delta/Gamma/Vega/Theta）—— 第74271行"))
    story.append(bullet("10000条路径的蒙卡模拟器 —— 第63857行"))
    story.append(Paragraph(
        "结论：不需要重新设计「压力情景构造 → 重新估值」的流程，"
        "应该直接调用现有估值函数做偏移计算。", s_warn))

    story.append(sp(2))
    story.append(Paragraph("问题二：7组价格×4组波动率=28个情景过于繁琐", s_h3))
    story.append(Paragraph(
        "计划书建议 7 个价格冲击 × 4 个波动率冲击 = 28 个情景逐一估值。"
        "对于MC类结构（雪球/累计/气囊），每个情景跑10000条路径×逐日状态机，"
        "单个结构可能需要30-60秒。这在录入时是不可接受的。", s_body))
    story.append(Paragraph(
        "建议：对香草用解析解做情景扫描（毫秒级）；"
        "对MC类结构用 Delta-Gamma 近似 + 少量关键情景校验。", s_warn))

    story.append(sp(2))
    story.append(Paragraph("问题三：VaR方案缺乏与现有MC的衔接", s_h3))
    story.append(Paragraph(
        "计划书将 VaR 定义为第二阶段独立模块，但实际上系统已有 MC 路径生成器"
        "（第63857行 winrate_simulate_price_paths）和路径估值引擎"
        "（第69740行 winrate_estimate_structure_path_values）。"
        "VaR 本质上就是这些路径终值的分位数计算，应该直接复用而非重建。", s_body))

    story.append(sp(2))
    story.append(Paragraph("问题四：未考虑计算性能", s_h3))
    story.append(Paragraph(
        "系统是 Streamlit 应用，用户操作时会阻塞。如果在结构录入时触发完整的"
        "SPAN-like 计算（28个MC情景），会导致页面卡顿数分钟。"
        "计划书未讨论异步计算、缓存策略或轻量近似方案。", s_body))

    story.append(sp(2))
    story.append(Paragraph("问题五：统一引擎设计过于庞大", s_h3))
    story.append(Paragraph(
        "StructureMarginEngine 输入包含10+字段，输出包含15+字段，"
        "加上诊断信息和分项明细，接口复杂度很高。"
        "建议按「快速预估 → 精确计算 → 诊断」分层，不要一次返回所有内容。", s_body))

    story.append(PageBreak())

    # ══════════════════════════════════════
    #  第三部分：优化方案
    # ══════════════════════════════════════
    story.append(Paragraph("第三部分  优化方案与建议", s_h1))
    story.append(hr())

    # 3.1
    story.append(Paragraph("3.1  核心理念：用现有估值体系替代纯 SPAN 构建", s_h2))
    story.append(Paragraph(
        "优化后的核心公式保持不变：", s_body))
    story.append(Paragraph(
        "建议保证金 = max(压力情景保证金, 最低保证金) + 附加项", s_code))
    story.append(Paragraph(
        "但「压力情景保证金」的计算方式应按结构类型分流，充分利用已有估值函数：", s_body))

    flow_data = [
        ["结构类型", "计算方法", "依赖函数", "预期耗时"],
        ["香草期权", "Black-76 解析解情景扫描\n(价格±15%/±10%/±5%, IV±5/±10)",
         "winrate_black76_\nvanilla_unit_price",
         "&lt;10ms"],
        ["TRS/线性", "线性Delta冲击\n(价格×冲击系数×数量)",
         "Delta计算",
         "&lt;1ms"],
        ["累计/气囊\n(8种)", "Delta-Gamma近似 +\n2-3个关键情景MC校验",
         "winrate_run_structure_\nvaluation + Greeks",
         "3-8秒"],
        ["雪球", "Delta-Gamma近似 +\n1个极端情景MC校验",
         "winrate_run_structure_\nvaluation + Greeks",
         "5-10秒"],
        ["凤凰累计", "Delta-Gamma近似 +\n2个关键情景MC校验",
         "winrate_run_structure_\nvaluation + Greeks",
         "5-10秒"],
    ]
    t_rows = []
    for i, row in enumerate(flow_data):
        if i == 0:
            t_rows.append([Paragraph(c, s_table_header) for c in row])
        else:
            t_rows.append([Paragraph(c.replace("\n", "<br/>"), s_table_cell) for c in row])
    ft = Table(t_rows, colWidths=[26*mm, 48*mm, 42*mm, W - 116*mm], repeatRows=1)
    ft.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ] + [("BACKGROUND", (0, i), (-1, i), C_ROW_ALT) for i in range(2, len(t_rows), 2)]))
    story.append(ft)

    story.append(sp(2))
    story.append(Paragraph("Delta-Gamma 近似公式：", s_h3))
    story.append(Paragraph(
        "ΔV ≈ Delta × ΔS + 0.5 × Gamma × (ΔS)² + Vega × Δσ + Theta × ΔT", s_code))
    story.append(Paragraph(
        "其中 Delta/Gamma/Vega/Theta 已由 winrate_run_structure_greeks_scan 计算。"
        "这个近似对单日冲击非常精确，且计算耗时仅为全MC的 1/100。", s_body))

    # 3.2
    story.append(Paragraph("3.2  分结构类型的保证金计算策略", s_h2))

    story.append(Paragraph("A. 香草期权 —— 解析解精确计算", s_h3))
    story.append(bullet("卖出看跌：保证金 ≈ max(期权费, 行权价×比例 - 虚值额) + 价格冲击"))
    story.append(bullet("卖出看涨：保证金 ≈ max(期权费, 标的×比例 - 虚值额) + 价格冲击"))
    story.append(bullet("买入期权：保证金 = 期权费（最大亏损锁定）"))
    story.append(bullet("直接用 Black-76 对 6-10 个情景逐一解析定价，总耗时 &lt; 10ms"))

    story.append(Paragraph("B. TRS / 线性结构 —— Delta 冲击", s_h3))
    story.append(bullet("保证金 = max(|价格冲击 × 名义数量|, 最低保证金)"))
    story.append(bullet("价格冲击取 ±10% 或 ±15%，线性计算无需 MC"))

    story.append(Paragraph("C. 累计类（8种）—— 近似 + 校验", s_h3))
    story.append(bullet("第一步：用现有 Greeks（第74271行）做 Delta-Gamma-Vega 近似"))
    story.append(bullet("第二步：取标的 ±10% 的 2 个极端情景做 MC 校验"))
    story.append(bullet("第三步：取近似值和校验值的较大者"))
    story.append(bullet("首次计算需 ~5秒（Greeks扫描 + 2次MC），后续可缓存"))

    story.append(Paragraph("D. 雪球 —— 近似 + 极端校验", s_h3))
    story.append(bullet("雪球的最大风险在敲入情景，重点关注标的下跌至敲入线的冲击"))
    story.append(bullet("用 Delta-Gamma 近似估算，加一个「标的跌至敲入价」的 MC 校验"))
    story.append(bullet("名义金额大的雪球，可额外加集中度附加"))

    story.append(Paragraph("E. 凤凰累计 —— 类似累计 + 敲入风险", s_h3))
    story.append(bullet("类似累计类处理，但额外关注敲入后的行权风险"))
    story.append(bullet("用 Delta-Gamma 近似 + 2个关键情景 MC 校验"))

    # 3.3
    story.append(Paragraph("3.3  极简用户输入设计", s_h2))
    story.append(Paragraph(
        "优化目标：用户在结构录入时，保证金部分「零新增输入」。", s_body))
    story.append(sp(1))
    story.append(Paragraph("方案：完全自动化 + 可覆盖", s_h3))
    story.append(bullet("结构参数填写完成后，系统自动计算建议保证金并展示"))
    story.append(bullet("现有4个保证金字段保持不变，含义从「手工输入」变为「自动计算值（可覆盖）」"))
    story.append(bullet("在保证金区域增加一个小 toggle：「自动计算 / 手工覆盖」"))
    story.append(bullet("默认「自动计算」，计算结果自动填入3个字段并联动"))
    story.append(bullet("切换到「手工覆盖」后，用户可自由编辑，系统不再覆盖"))
    story.append(sp(1))

    story.append(Paragraph("对比 Codex 方案：", s_h3))
    compare_data = [
        ["项目", "Codex方案", "优化方案"],
        ["新增录入字段", "1个（保证金口径选择）", "0个（toggle切换）"],
        ["计算触发时机", "录入结构参数后", "同左，但增加防抖（参数变化后500ms）"],
        ["用户等待", "未说明", "展示计算中状态，香草&lt;1s，复杂结构3-10s"],
        ["覆盖方式", "手工覆盖模式", "toggle切换 + 直接编辑字段"],
    ]
    story.append(make_table(compare_data[0], compare_data[1:], [32*mm, 44*mm, W - 76*mm]))

    # 3.4
    story.append(PageBreak())
    story.append(Paragraph("3.4  统一保证金引擎优化设计", s_h2))
    story.append(Paragraph(
        "将 Codex 的 StructureMarginEngine 简化为三层架构：", s_body))

    story.append(Paragraph("第一层：快速预估（QuickEstimate）", s_h3))
    story.append(bullet("输入：结构类型 + 基础参数（入场价/行权价/数量/IV）"))
    story.append(bullet("方法：香草走解析、TRS走线性、复杂结构走 Delta-Gamma 近似"))
    story.append(bullet("输出：margin_estimate, method_used"))
    story.append(bullet("耗时：&lt; 100ms，用于实时 UI 反馈"))

    story.append(Paragraph("第二层：精确计算（PreciseCalc）", s_h3))
    story.append(bullet("输入：QuickEstimate 结果 + 完整结构参数 + 价格数据"))
    story.append(bullet("方法：2-3个关键情景 MC 校验 + 取大"))
    story.append(bullet("输出：span_margin, max_loss_scenario, scenario_details"))
    story.append(bullet("耗时：3-10s，用于保存前确认"))

    story.append(Paragraph("第三层：诊断信息（Diagnostics）", s_h3))
    story.append(bullet("输入：PreciseCalc 结果"))
    story.append(bullet("输出：情景损益明细、Greeks、与手工值对比"))
    story.append(bullet("仅在用户点击查看时才计算"))

    story.append(sp(2))
    story.append(Paragraph("Engine 简化接口设计：", s_h3))
    code_text = (
        "class StructureMarginEngine:<br/>"
        "    def quick_estimate(struct_type, params) → {margin, method}<br/>"
        "    def precise_calc(struct_type, params, prices) → {margin, scenario, details}<br/>"
        "    def diagnostics(result) → {scenarios, greeks, breakdown}<br/>"
        "    <br/>"
        "    # 输出统一为：<br/>"
        "    {<br/>"
        "      margin_amount_wan: float    # 万元<br/>"
        "      margin_per_ton: float       # 元/吨<br/>"
        "      margin_rate_pct: float      # 占比%<br/>"
        "      method: str                 # 'span_analytic' | 'span_mc' | 'delta_gamma'<br/>"
        "      max_loss_scenario: str      # 最大亏损情景描述<br/>"
        "    }"
    )
    story.append(Paragraph(code_text, s_code))

    # 3.5
    story.append(Paragraph("3.5  后台配置与数据存储", s_h2))
    story.append(Paragraph(
        "高级参数存储在 app_kv 表中（已有的 KV 存储机制），"
        "通过系统设置页面配置，不影响结构录入界面。", s_body))

    config_data = [
        ["配置项", "默认值", "说明"],
        ["margin.price_shock_levels", "[-15,-10,-5,0,5,10,15]", "价格冲击水平(%)"],
        ["margin.vol_shock_levels", "[-5,0,5,10]", "波动率冲击(vol)"],
        ["margin.min_margin_rate_pct", "5.0", "最低保证金比例(%)"],
        ["margin.mc_paths", "5000", "MC路径数（精确计算用）"],
        ["margin.mc_seed", "42", "MC随机种子（确保可重复）"],
        ["margin.time_roll_days", "1", "时间滚动天数"],
        ["margin.var_confidence", "0.99", "VaR置信水平（二期）"],
        ["margin.var_holding_days", "1", "VaR持有期（二期）"],
        ["margin.funding_rate_pct", "3.5", "资金成本利率(%)（三期）"],
        ["margin.concentration_limit_wan", "5000", "集中度阈值(万元)"],
        ["margin.liquidity_surcharge_pct", "0", "流动性附加(%)"],
    ]
    story.append(make_table(config_data[0], config_data[1:], [50*mm, 38*mm, W - 88*mm]))

    story.append(sp(2))
    story.append(Paragraph("数据存储扩展：", s_h3))
    story.append(bullet("结构表 structure.params_json 中增加 margin_calc 嵌套字段"))
    story.append(bullet("存储计算结果快照：method, margin_wan, per_ton, rate_pct, max_scenario"))
    story.append(bullet("存储计算时间戳，用于「是否需要重新计算」判断"))
    story.append(bullet("手动覆盖时，margin_calc.overridden = true"))

    # 3.6
    story.append(Paragraph("3.6  改进后的分阶段开发计划", s_h2))

    story.append(Paragraph("第一阶段：基础自动保证金（建议 2 周）", s_h3))
    phase1 = [
        ["步骤", "内容", "工作量", "依赖"],
        ["P1.1", "新增 margin_config 表/配置项\n（app_kv存储SPan参数）", "0.5天", "无"],
        ["P1.2", "新增 StructureMarginEngine\n· quick_estimate 方法\n· 香草解析路径", "1天", "P1.1"],
        ["P1.3", "扩展 Engine：TRS线性路径", "0.5天", "P1.2"],
        ["P1.4", "扩展 Engine：累计/气囊\nDelta-Gamma近似路径", "1.5天", "P1.2\n+Greeks"],
        ["P1.5", "扩展 Engine：雪球/凤凰\n近似+校验路径", "1.5天", "P1.4"],
        ["P1.6", "UI改造：保证金toggle +\n自动回填 + 计算中状态", "1.5天", "P1.2"],
        ["P1.7", "报价图增加自动保证金展示", "0.5天", "P1.6"],
        ["P1.8", "单元测试 + 集成测试", "1天", "P1.1-P1.7"],
    ]
    t_rows = []
    for i, row in enumerate(phase1):
        if i == 0:
            t_rows.append([Paragraph(c, s_table_header) for c in row])
        else:
            t_rows.append([Paragraph(c.replace("\n", "<br/>"), s_table_cell) for c in row])
    pt = Table(t_rows, colWidths=[14*mm, 52*mm, 22*mm, W - 88*mm], repeatRows=1)
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ] + [("BACKGROUND", (0, i), (-1, i), C_ROW_ALT) for i in range(2, len(t_rows), 2)]))
    story.append(pt)

    story.append(sp(3))
    story.append(Paragraph("第二阶段：VaR + 精确计算（建议 1.5 周）", s_h3))
    phase2_items = [
        "复用 winrate_simulate_price_paths 生成 MC 路径",
        "复用 winrate_estimate_structure_path_values 做路径估值",
        "取路径终值的 P99 分位数作为 VaR 保证金",
        "VaR 不足时自动退回 SPAN-like（Delta-Gamma近似）",
        "监控计算页面增加存续结构保证金占用展示",
        "仓库页面增加按标的/结构汇总的保证金视图",
    ]
    for item in phase2_items:
        story.append(bullet(item))

    story.append(sp(3))
    story.append(Paragraph("第三阶段：资金成本进报价（建议 1 周）", s_h3))
    phase3_items = [
        "资金成本 = 保证金 × 资金利率 × 持有天数 / 365",
        "自助报价结果增加「含资金成本报价」",
        "报价图增加资金成本行",
    ]
    for item in phase3_items:
        story.append(bullet(item))

    story.append(PageBreak())

    # ══════════════════════════════════════
    #  第四部分：详细技术方案
    # ══════════════════════════════════════
    story.append(Paragraph("第四部分  详细技术方案", s_h1))
    story.append(hr())

    # 4.1
    story.append(Paragraph("4.1  函数复用映射表", s_h2))
    story.append(Paragraph(
        "以下是保证金计算引擎各步骤与现有函数的精确映射关系：", s_body))

    mapping_data = [
        ["计算步骤", "复用函数", "行号", "调用方式"],
        ["构建压力情景", "手动构造\nprice_shift × iv_shift", "—", "新增函数"],
        ["香草情景重估", "winrate_black76_\nvanilla_unit_price", "65323",
         "直接调用，解析解"],
        ["累计/气囊\n情景近似", "winrate_run_structure_\ngreeks_scan → 插值", "74271",
         "获取Greeks后\n做Delta-Gamma近似"],
        ["累计/气囊\n情景精确校验", "winrate_run_structure_\nvaluation", "70094",
         "对2-3个关键情景\n运行MC估值"],
        ["雪球情景校验", "winrate_run_structure_\nvaluation", "70094",
         "对敲入极端情景\n运行MC估值"],
        ["VaR路径生成", "winrate_simulate_\nprice_paths", "63857",
         "复用，二期使用"],
        ["VaR路径估值", "winrate_estimate_\nstructure_path_values", "69740",
         "复用，二期使用"],
        ["结果回填", "resolve_structure_\nmargin_linked_values", "25980",
         "已有的联动函数"],
        ["单位换算", "structure_margin_\nwan_from_per_ton", "25941",
         "已有的换算函数"],
    ]
    t_rows = []
    for i, row in enumerate(mapping_data):
        if i == 0:
            t_rows.append([Paragraph(c, s_table_header) for c in row])
        else:
            t_rows.append([Paragraph(c.replace("\n", "<br/>"), s_table_cell) for c in row])
    mt = Table(t_rows, colWidths=[30*mm, 38*mm, 16*mm, W - 84*mm], repeatRows=1)
    mt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ] + [("BACKGROUND", (0, i), (-1, i), C_ROW_ALT) for i in range(2, len(t_rows), 2)]))
    story.append(mt)

    # 4.2
    story.append(Paragraph("4.2  数据流设计", s_h2))
    story.append(Paragraph("优化后的保证金数据流：", s_h3))
    flow_code = (
        "[结构录入 UI]<br/>"
        "  用户填写结构参数（入场价/行权价/数量/IV/方向等）<br/>"
        "  ↓ 参数变化触发防抖（500ms）<br/>"
        "[StructureMarginEngine.quick_estimate()]<br/>"
        "  ├─ 香草 → Black-76 解析情景扫描（&lt;10ms）<br/>"
        "  ├─ TRS → 线性Delta冲击（&lt;1ms）<br/>"
        "  └─ 累计/雪球/气囊 → Delta-Gamma近似（&lt;100ms）<br/>"
        "  ↓ 实时回填保证金字段<br/>"
        "[UI 展示] 保证金区域显示建议值 + 计算方法标签<br/>"
        "  ↓ 用户点击「保存」<br/>"
        "[StructureMarginEngine.precise_calc()]（仅复杂结构）<br/>"
        "  → 2-3个关键情景MC校验（3-10s，带进度条）<br/>"
        "  → 取近似值和校验值的较大者<br/>"
        "  ↓ 最终结果写入<br/>"
        "[resolve_structure_margin_linked_values() → merge_structure_margin_payload()]<br/>"
        "  → params_json.margin_calc = {method, margin, scenario, ts}<br/>"
        "  → 现有4个保证金字段联动更新<br/>"
        "  → quote_payload → 报价图渲染"
    )
    story.append(Paragraph(flow_code, s_code))

    # 4.3
    story.append(Paragraph("4.3  UI 接入方案", s_h2))

    story.append(Paragraph("A. 结构录入页面改造（第83620行附近）", s_h3))
    ui_changes = [
        ["位置", "改造内容", "说明"],
        ["保证金区域上方", "增加 toggle：自动计算/手工覆盖", "默认自动计算"],
        ["保证金区域", "增加计算状态指示器", "计算中/已完成/已覆盖"],
        ["保证金字段", "自动模式：显示建议值（灰色不可编辑）\n覆盖模式：可编辑（白色背景）",
         "视觉区分两种模式"],
        ["保证金区域下方", "增加「查看计算口径」折叠面板", "展示最大情景、Greeks、情景明细"],
        ["报价图预览", "保证金行增加来源标签", "(自动) 或 (手工)"],
    ]
    t_rows = []
    for i, row in enumerate(ui_changes):
        if i == 0:
            t_rows.append([Paragraph(c, s_table_header) for c in row])
        else:
            t_rows.append([Paragraph(c.replace("\n", "<br/>"), s_table_cell) for c in row])
    ut = Table(t_rows, colWidths=[30*mm, 60*mm, W - 90*mm], repeatRows=1)
    ut.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ] + [("BACKGROUND", (0, i), (-1, i), C_ROW_ALT) for i in range(2, len(t_rows), 2)]))
    story.append(ut)

    story.append(sp(2))
    story.append(Paragraph("B. 自助报价页面改造（第76677行附近）", s_h3))
    story.append(bullet("计算理论价后同步调用 quick_estimate 计算保证金"))
    story.append(bullet("结果表增加「建议保证金」「单吨保证金」「保证金比例」三列"))
    story.append(bullet("报价图片输出增加保证金行（已有基础，复用 show_margin=True）"))

    story.append(sp(2))
    story.append(Paragraph("C. 监控计算页面改造（第92564行附近）", s_h3))
    story.append(bullet("存续结构表增加「自动保证金」列"))
    story.append(bullet("按风险子/标的/结构汇总保证金占用"))
    story.append(bullet("展示总保证金、保证金变化、集中度指标"))

    story.append(sp(2))
    story.append(Paragraph("D. 期权仓库页面改造（第87943行附近）", s_h3))
    story.append(bullet("仓库概览卡片增加「结构保证金占用」"))
    story.append(bullet("按标的分组的保证金汇总"))
    story.append(bullet("替代现有的简化「最大侧×均价×比例」算法"))

    # 4.4
    story.append(Paragraph("4.4  验收标准优化", s_h2))
    story.append(Paragraph(
        "在 Codex 原有验收标准基础上，增加以下关键验收项：", s_body))

    accept_data = [
        ["类别", "验收项", "判定标准"],
        ["正确性", "同一结构多次计算结果一致", "随机种子固定，MC路径可重复"],
        ["正确性", "卖出期权保证金 ＞ 买入期权", "香草卖put保证金 ＞ 买put保证金"],
        ["正确性", "标的冲击越大，保证金不应反向下降", "单调性验证"],
        ["正确性", "数量翻倍，保证金大致翻倍（±5%）", "线性度验证"],
        ["正确性", "极端情景可解释", "最大情景输出含标的变动方向和幅度"],
        ["性能", "香草期权计算耗时 ＜ 100ms", "解析解"],
        ["性能", "复杂结构快速预估 ＜ 500ms", "Delta-Gamma近似"],
        ["性能", "精确计算 ＜ 15秒", "含MC校验"],
        ["鲁棒性", "历史数据缺失不报错", "自动退回近似计算"],
        ["鲁棒性", "手工覆盖后不被自动覆盖", "overridden标记保护"],
        ["鲁棒性", "参数边界值不崩溃", "IV=0、数量=0、价格=0"],
        ["易用性", "零新增必填输入", "toggle切换即可"],
        ["易用性", "计算状态有明确反馈", "loading/完成/覆盖状态"],
    ]
    story.append(make_table(accept_data[0], accept_data[1:], [18*mm, 50*mm, W - 68*mm]))

    story.append(PageBreak())

    # ─── 附录 ───
    story.append(Paragraph("附录  关键代码位置索引", s_h1))
    story.append(hr())

    index_data = [
        ["内容", "文件", "行号"],
        ["保证金字段常量定义", "app.py", "276-285"],
        ["保证金换算函数", "app.py", "25941-25970"],
        ["保证金联动核心", "app.py", "25980-26010"],
        ["保证金Payload标准化", "app.py", "26013-26182"],
        ["仓库保证金算法", "app.py", "54981-55080"],
        ["结构录入保证金UI", "app.py", "83620-83746"],
        ["报价图保证金渲染", "app.py", "21772-21795"],
        ["仓库保证金参数", "app.py", "88015-88035"],
        ["Black-76 定价核心", "app.py", "65323"],
        ["结构MC估值入口", "app.py", "70094"],
        ["路径估值引擎", "app.py", "69740"],
        ["MC价格路径生成", "app.py", "63857"],
        ["风险中性MC路径", "app.py", "69226"],
        ["Greeks扫描", "app.py", "74271"],
        ["Greeks快照", "app.py", "73159-73217"],
        ["IV反推（香草）", "app.py", "65510"],
        ["IV反推（复杂结构）", "app.py", "66322"],
        ["正态CDF", "app.py", "65319"],
        ["StructureSpec定义", "app.py", "22307-22316"],
        ["STRUCTURE_REGISTRY", "app.py", "24269-24435"],
        ["结构状态机(雪球)", "app.py", "23294"],
        ["结构状态机(TRS)", "app.py", "23997"],
        ["结构状态机(香草)", "app.py", "24025"],
        ["凤凰台账模拟", "app.py", "25023"],
        ["报价图渲染函数", "app.py", "21278"],
        ["自助报价页面", "app.py", "76677-76869"],
        ["监控计算页面", "app.py", "92564"],
        ["DB app_kv表", "app.py", "131-150"],
        ["DB structure表", "app.py", "778-821"],
        ["CVaR尾部风险", "app.py", "44020-44635"],
        ["估值系统保证金注释", "app.py", "74108"],
    ]
    story.append(make_table(index_data[0], index_data[1:], [52*mm, 20*mm, W - 72*mm]))

    story.append(sp(5))
    story.append(hr())
    story.append(Paragraph(
        "本报告基于对 CH场外期权结构风险管理监控系统 V8.2 全部源码的分析生成。<br/>"
        "报告日期：2026-05-12 &nbsp;&nbsp;|&nbsp;&nbsp; 分析范围：app.py 全部 95,096 行代码",
        s_footer))

    # ── 生成 PDF ──
    doc.build(story)
    return output_path


if __name__ == "__main__":
    out = build_report("d:/biancheng/output/保证金计算功能_开发方案与系统分析报告.pdf")
    print(f"PDF 已生成: {out}")
