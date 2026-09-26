"""모델 v2.2와 같은 조사량(842 사용자·일)의 무작위 선택을 비교하는 README용 그림.

입력: random_baseline_summary.csv (random_baseline.py 결과)
출력: images/random_baseline_comparison.png
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[2] / "images" / "random_baseline_comparison.png"

MODEL, RANDOM = "#2a78d6", "#a3a29d"
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False})

s = pd.read_csv(HERE / "random_baseline_summary.csv", encoding="utf-8-sig").set_index("metric")
panels = [
    ("detected", "사건기간 안에 탐지한 내부자 (70명 중)", "명", "많을수록 좋음"),
    ("nonins_fp_users", "경보를 받은 비내부자 (905명 중)", "명", "적을수록 좋음"),
]

fig, axes = plt.subplots(1, 2, figsize=(11, 3.4), facecolor=SURFACE)
for ax, (metric, title, unit, note) in zip(axes, panels):
    r = s.loc[metric]
    vals = [r.model_v2_2, r.random_mean]
    ax.barh([1, 0], vals, height=0.52, color=[MODEL, RANDOM])
    ax.errorbar(r.random_mean, 0, xerr=[[r.random_mean - r.random_p2_5], [r.random_p97_5 - r.random_mean]],
                fmt="none", ecolor=INK_2, elinewidth=1.4, capsize=5)
    top = max(r.model_v2_2, r.random_p97_5)
    ax.text(r.model_v2_2 + top * 0.02, 1, f"{r.model_v2_2:,.0f}{unit}", va="center", color=INK, fontsize=12, weight="bold")
    ax.text(r.random_p97_5 + top * 0.02, 0,
            f"{r.random_mean:,.1f}{unit}  (95% 범위 {r.random_p2_5:,.0f}~{r.random_p97_5:,.0f})",
            va="center", color=INK_2, fontsize=10)
    ax.set_yticks([1, 0], ["모델 v2.2", "무작위 평균\n(2,000회)"], color=INK, fontsize=11)
    ax.set_xlim(0, top * 1.55)
    ax.set_title(title, loc="left", color=INK, fontsize=12.5, weight="bold", pad=24)
    ax.text(0, 1.03, note, transform=ax.transAxes, color=INK_2, fontsize=9.5, ha="left", va="bottom")
    ax.set_facecolor(SURFACE)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", colors=INK_2, labelsize=9)
    ax.tick_params(axis="y", length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)

fig.text(0.01, -0.04, "같은 조사량 = 평가기간 225,281 사용자·일 중 842 사용자·일을 선택. "
         "평가기간 2010-06-01 ~ 2011-05-17, 데이터: CERT r4.2 (합성)",
         color=INK_2, fontsize=9)
fig.tight_layout(w_pad=4)
OUT.parent.mkdir(exist_ok=True)
fig.savefig(OUT, dpi=160, bbox_inches="tight", facecolor=SURFACE)
print(OUT)
