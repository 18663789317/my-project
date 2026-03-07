from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


OUT_PATH = Path("output_images") / "airbag_fullpage_new_template_preview.png"


def draw_box(
    ax,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    fc: str = "#10274b",
    ec: str = "#274670",
    lw: float = 1.0,
    rad: float = 0.012,
) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle=f"round,pad=0.006,rounding_size={rad}",
            linewidth=lw,
            edgecolor=ec,
            facecolor=fc,
        )
    )


def main() -> None:
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    fig = plt.figure(figsize=(16.8, 11.8), dpi=180, facecolor="#071327")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#071327")
    ax.axis("off")

    ax.text(0.04, 0.94, "G001 - 雪球监控 | 全部品种 | 2026-03-03", color="white", fontsize=22, weight="bold")

    draw_box(ax, 0.03, 0.06, 0.94, 0.86, fc="#0b1d39", ec="#153660", lw=1.1)

    # 顶部 KPI 区
    bar_x, bar_y, bar_w, bar_h = 0.05, 0.78, 0.90, 0.12
    draw_box(ax, bar_x, bar_y, bar_w, bar_h, fc="#10274b", ec="#2a4f79")
    kpi_titles = ["当日净生成(吨)", "当日多/空生成(吨)", "净空头生成均价", "净方向", "当日收盘价"]
    kpi_values = ["-20,000.00", "多 0.00 / 空 20,000.00", "755.00", "空单", "800.00"]
    kpi_colors = ["#ff7b72", "#dbe7f5", "#dbe7f5", "#8ad2ff", "#9fd3ff"]
    col_ratios = [0.18, 0.30, 0.20, 0.15, 0.17]
    col_edges = [bar_x]
    for r in col_ratios:
        col_edges.append(col_edges[-1] + bar_w * r)
    for i in range(5):
        x0 = col_edges[i]
        if i > 0:
            ax.plot([x0, x0], [bar_y + 0.02, bar_y + bar_h - 0.02], color="#1f3b63", linewidth=1.1)
        ax.text(x0 + 0.012, bar_y + bar_h - 0.043, kpi_titles[i], color="#a8bed7", fontsize=13.2)
        value_fs = 23 if i == 1 else 26
        ax.text(x0 + 0.012, bar_y + 0.032, kpi_values[i], color=kpi_colors[i], fontsize=value_fs, weight="bold")

    # 左侧净风险卡
    left_x, left_y, left_w, left_h = 0.05, 0.14, 0.20, 0.61
    draw_box(ax, left_x, left_y, left_w, left_h, fc="#0f2343", ec="#264a74")
    ax.text(left_x + 0.015, left_y + left_h - 0.04, "净风险结论", color="#dbe7f5", fontsize=20, weight="bold")
    ax.text(left_x + left_w / 2, left_y + left_h - 0.10, "剩余最大（净敞口）", color="#a8bed7", fontsize=13.2, ha="center", weight="bold")
    ax.text(left_x + left_w / 2, left_y + left_h - 0.20, "+0.00 吨", color="#dbe7f5", fontsize=28, ha="center", weight="bold")
    ax.text(left_x + left_w / 2, left_y + 0.22, "方向 = 中性", color="#dbe7f5", fontsize=22, ha="center", weight="bold")
    ax.plot([left_x + 0.012, left_x + left_w - 0.012], [left_y + 0.19, left_y + 0.19], color="#1f3b63", linewidth=1.0)
    ax.text(left_x + 0.015, left_y + 0.15, "当日多空对锁", color="#dbe7f5", fontsize=13, weight="bold")
    ax.text(left_x + 0.015, left_y + 0.10, "对锁数量（吨）", color="#a8bed7", fontsize=11.5, weight="bold")
    ax.text(left_x + left_w - 0.015, left_y + 0.10, "0.00", color="#dbe7f5", fontsize=18, weight="bold", ha="right")
    ax.text(left_x + 0.015, left_y + 0.04, "对锁利润", color="#a8bed7", fontsize=11.5, weight="bold")
    ax.text(left_x + left_w - 0.015, left_y + 0.04, "0.00", color="#ffd166", fontsize=18, weight="bold", ha="right")

    # 右侧：Top5 + 雪球 + 气囊
    right_x, right_y, right_w, right_h = 0.26, 0.14, 0.69, 0.61
    draw_box(ax, right_x, right_y, right_w, right_h, fc="#0f2343", ec="#264a74")

    # Top5
    top_x, top_y, top_w, top_h = right_x + 0.01, right_y + 0.36, right_w - 0.02, 0.23
    draw_box(ax, top_x, top_y, top_w, top_h, fc="#10274b", ec="#264a74")
    ax.text(top_x + 0.012, top_y + top_h - 0.032, "风险暴露 Top5 结构", color="#dbe7f5", fontsize=21, weight="bold")
    header_y = top_y + top_h - 0.075
    draw_box(ax, top_x + 0.008, header_y - 0.028, top_w - 0.016, 0.032, fc="#163157", ec="#2d4f7a")
    ax.text(top_x + 0.014, header_y - 0.009, "结构详情", color="#a8bed7", fontsize=12.0, weight="bold")
    ax.text(top_x + 0.42, header_y - 0.009, "状态", color="#a8bed7", fontsize=12.0, weight="bold", ha="center")
    ax.text(top_x + 0.50, header_y - 0.009, "剩余最大", color="#a8bed7", fontsize=12.0, weight="bold", ha="center")
    ax.text(top_x + 0.58, header_y - 0.009, "剩余天", color="#a8bed7", fontsize=12.0, weight="bold", ha="center")
    ax.text(top_x + 0.66, header_y - 0.009, "当日生成", color="#a8bed7", fontsize=12.0, weight="bold", ha="right")
    ax.text(top_x + 0.73, header_y - 0.009, "总吨数", color="#a8bed7", fontsize=12.0, weight="bold", ha="right")
    row_y = header_y - 0.076
    draw_box(ax, top_x + 0.008, row_y, top_w - 0.016, 0.052, fc="#112a4d", ec="#22466f")
    ax.text(top_x + 0.014, row_y + 0.017, "S023-看跌安全气囊-海证资本-障碍价（795）-入场价（755）", color="white", fontsize=12.5, weight="bold")
    ax.text(top_x + 0.42, row_y + 0.017, "当日不生成", color="#dbe7f5", fontsize=12.2, ha="center")
    ax.text(top_x + 0.50, row_y + 0.017, "+20,000.00", color="#ffd166", fontsize=12.3, weight="bold", ha="center")
    ax.text(top_x + 0.58, row_y + 0.017, "19", color="#dbe7f5", fontsize=12.2, ha="center")
    ax.text(top_x + 0.66, row_y + 0.017, "0.00", color="#dbe7f5", fontsize=12.2, ha="right")
    ax.text(top_x + 0.73, row_y + 0.017, "0.00", color="#dbe7f5", fontsize=12.2, ha="right")
    ax.plot([top_x + 0.012, top_x + top_w - 0.012], [top_y + 0.035, top_y + 0.035], color="#1f3b63", linewidth=1.0)
    ax.text(top_x + 0.012, top_y + 0.015, "当日生成合计", color="#a8bed7", fontsize=12.2, weight="bold")
    ax.text(top_x + top_w - 0.012, top_y + 0.015, "0.00", color="#dbe7f5", fontsize=13.5, weight="bold", ha="right")

    # 雪球结构监控
    sb_x, sb_y, sb_w, sb_h = right_x + 0.01, right_y + 0.19, right_w - 0.02, 0.15
    draw_box(ax, sb_x, sb_y, sb_w, sb_h, fc="#10274b", ec="#264a74")
    ax.text(sb_x + 0.012, sb_y + sb_h - 0.03, "雪球结构监控", color="#dbe7f5", fontsize=20, weight="bold")
    draw_box(ax, sb_x + 0.008, sb_y + sb_h - 0.068, sb_w - 0.016, 0.03, fc="#163157", ec="#2d4f7a")
    ax.text(sb_x + 0.014, sb_y + sb_h - 0.049, "结构详情", color="#a8bed7", fontsize=11.8, weight="bold")
    ax.text(sb_x + 0.43, sb_y + sb_h - 0.049, "状态", color="#a8bed7", fontsize=11.8, ha="center", weight="bold")
    ax.text(sb_x + 0.51, sb_y + sb_h - 0.049, "距离敲入", color="#a8bed7", fontsize=11.8, ha="center", weight="bold")
    ax.text(sb_x + 0.58, sb_y + sb_h - 0.049, "已累票息", color="#ff7b72", fontsize=11.8, ha="center", weight="bold")
    ax.text(sb_x + 0.66, sb_y + sb_h - 0.049, "剩余自然日", color="#a8bed7", fontsize=11.8, ha="center", weight="bold")
    draw_box(ax, sb_x + 0.008, sb_y + 0.035, sb_w - 0.016, 0.048, fc="#112a4d", ec="#22466f")
    ax.text(sb_x + 0.014, sb_y + 0.052, "S018-看涨雪球-中证资本-敲入价（2956.3）-入场价（3145）", color="white", fontsize=12.0, weight="bold")
    ax.text(sb_x + 0.43, sb_y + 0.052, "雪球观察中", color="#dbe7f5", fontsize=11.8, ha="center")
    ax.text(sb_x + 0.51, sb_y + 0.052, "110.70 (3.52%)", color="#dbe7f5", fontsize=11.8, ha="center")
    ax.text(sb_x + 0.58, sb_y + 0.052, "207,342.47", color="#ff4d4f", fontsize=11.9, ha="center", weight="bold")
    ax.text(sb_x + 0.66, sb_y + 0.052, "20", color="#dbe7f5", fontsize=11.8, ha="center")
    ax.text(sb_x + 0.012, sb_y + 0.007, "已累票息合计", color="#a8bed7", fontsize=12.0, weight="bold")
    ax.text(sb_x + sb_w - 0.012, sb_y + 0.007, "207,342.47", color="#7ee787", fontsize=13.2, ha="right", weight="bold")

    # 气囊结构监控（新增模板块，含已终止但仍有头寸）
    ab_x, ab_y, ab_w, ab_h = right_x + 0.01, right_y + 0.02, right_w - 0.02, 0.14
    draw_box(ax, ab_x, ab_y, ab_w, ab_h, fc="#10274b", ec="#264a74")
    ax.text(ab_x + 0.012, ab_y + ab_h - 0.03, "气囊结构监控（含已终止但仍有头寸）", color="#dbe7f5", fontsize=20, weight="bold")
    draw_box(ax, ab_x + 0.008, ab_y + ab_h - 0.067, ab_w - 0.016, 0.03, fc="#163157", ec="#2d4f7a")
    ax.text(ab_x + 0.014, ab_y + ab_h - 0.048, "结构详情", color="#a8bed7", fontsize=11.8, weight="bold")
    ax.text(ab_x + 0.43, ab_y + ab_h - 0.048, "状态", color="#a8bed7", fontsize=11.8, weight="bold", ha="center")
    ax.text(ab_x + 0.51, ab_y + ab_h - 0.048, "剩余数量", color="#a8bed7", fontsize=11.8, weight="bold", ha="center")
    ax.text(ab_x + 0.59, ab_y + ab_h - 0.048, "距离敲入", color="#a8bed7", fontsize=11.8, weight="bold", ha="center")
    ax.text(ab_x + 0.67, ab_y + ab_h - 0.048, "剩余自然日", color="#a8bed7", fontsize=11.8, weight="bold", ha="center")
    draw_box(ax, ab_x + 0.008, ab_y + 0.033, ab_w - 0.016, 0.045, fc="#112a4d", ec="#22466f")
    ax.text(ab_x + 0.014, ab_y + 0.048, "S023-看跌安全气囊-海证资本-障碍价（795）-入场价（755）", color="white", fontsize=11.8, weight="bold")
    ax.text(ab_x + 0.43, ab_y + 0.048, "已终止(有头寸)", color="#ffd166", fontsize=11.8, ha="center", weight="bold")
    ax.text(ab_x + 0.51, ab_y + 0.048, "20,000.00", color="#dbe7f5", fontsize=11.8, ha="center")
    ax.text(ab_x + 0.59, ab_y + 0.048, "+40.00 (5.30%)", color="#7ee787", fontsize=11.8, ha="center")
    ax.text(ab_x + 0.67, ab_y + 0.048, "27", color="#dbe7f5", fontsize=11.8, ha="center")
    ax.text(ab_x + 0.012, ab_y + 0.006, "气囊剩余数量合计", color="#a8bed7", fontsize=11.8, weight="bold")
    ax.text(ab_x + ab_w - 0.012, ab_y + 0.006, "20,000.00", color="#7ee787", fontsize=12.8, ha="right", weight="bold")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(str(OUT_PATH.resolve()))


if __name__ == "__main__":
    main()
