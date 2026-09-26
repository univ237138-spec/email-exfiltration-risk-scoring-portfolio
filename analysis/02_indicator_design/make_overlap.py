"""점수지표 8개 중복 검토: 상관 히트맵 + VIF (1×2, PNG + SVG). 새 계산 없이 기존 결과 CSV를 그림으로 옮김.

실행: 프로젝트 루트에서 python outputs/figures/발표자료/make_overlap.py
- 상관: experiments/20260922_9개지표_상관분석/07_eight_scoring_input.csv (점수 입력 기준 Pearson, 308,023 사용자·일)
         원건수 비교값은 같은 폴더 05_eight_raw_pearson.csv
- VIF:  experiments/20260923_로지스틱_통계분석/vif.csv (보정 이후 225,281 사용자·일)
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CORR_DIR = ROOT / "experiments/20260922_9개지표_상관분석"

INK, MUTED, GRID = "#1f2933", "#6b7785", "#eceff2"
BAR_Z, BAR_RULE, CUT_C = "#2f6db0", "#8d97a3", "#c8323c"

# z-score형 6개 → 규칙형 2개 순서. (CSV 라벨, 그림 라벨)
ORDER = [
    ("회사계정 외부 발송", "회사 계정 외부 발송"),
    ("신규 외부 수신자", "신규 외부 수신자"),
    ("회사계정 외부 첨부", "회사 계정 외부 첨부"),
    ("개인계정 첨부", "개인 계정 첨부"),
    ("다른 PC 로그온", "다른 PC 로그온"),
    ("야간 로그온", "야간 로그온"),
    ("구직 키워드 메일", "구직 키워드 메일"),
    ("야간 메일", "새로운 야간 메일"),  # 07 CSV의 '야간 메일' = 새로운 야간 메일 점수 조건(0/1)
]
N_Z = 6
MAX_PAIRS = [("회사계정 외부 발송", "회사계정 외부 첨부"), ("다른 PC 로그온", "야간 로그온")]

src = [s for s, _ in ORDER]
labels = [l for _, l in ORDER]
corr = pd.read_csv(CORR_DIR / "07_eight_scoring_input.csv", index_col=0).loc[src, src]
raw = pd.read_csv(CORR_DIR / "05_eight_raw_pearson.csv", index_col=0)
vif = pd.read_csv(ROOT / "experiments/20260923_로지스틱_통계분석/vif.csv")
vif_map = dict(zip(vif.label.str.replace("회사계정", "회사 계정").str.replace("개인계정", "개인 계정"), vif.VIF))
vif_vals = [vif_map[l] for l in labels]

fig = plt.figure(figsize=(16, 9), dpi=150)
fig.patch.set_facecolor("white")
ax_h = fig.add_axes([0.155, 0.235, 0.44, 0.61])
ax_v = fig.add_axes([0.77, 0.235, 0.2, 0.61])


def header(ax, title, line, x_off=0):
    ax.annotate(title, (0, 1), xycoords="axes fraction", xytext=(x_off, 34), textcoords="offset points",
                ha="left", va="bottom", fontsize=17, fontweight="bold", color=INK)
    ax.annotate(line, (0, 1), xycoords="axes fraction", xytext=(x_off, 10), textcoords="offset points",
                ha="left", va="bottom", fontsize=12, fontweight="bold", color=INK)


# ── 왼쪽: 상관 히트맵 ──
m = corr.to_numpy()
n = len(labels)
ax_h.imshow(m, cmap="RdBu_r", vmin=-1, vmax=1)
for i in range(n):
    for j in range(n):
        v = m[i, j]
        diag = i == j
        ax_h.text(j, i, "—" if diag else f"{0 if abs(v) < 0.005 else v:.2f}", ha="center", va="center", fontsize=10.5,
                  color="white" if abs(v) > 0.6 else (MUTED if diag else INK),
                  fontweight="bold" if (not diag and abs(v) >= 0.4) else "normal")
ax_h.set_xticks(range(n), labels, rotation=35, ha="right", fontsize=10.5, color=INK)
ax_h.set_yticks(range(n), labels, fontsize=10.5, color=INK)
ax_h.tick_params(length=0)
for s in ax_h.spines.values():
    s.set_visible(False)
ax_h.set_xticks(np.arange(n + 1) - 0.5, minor=True)
ax_h.set_yticks(np.arange(n + 1) - 0.5, minor=True)
ax_h.grid(which="minor", color="white", lw=2)
ax_h.tick_params(which="minor", length=0)
# z형 | 규칙형 구분선
ax_h.axhline(N_Z - 0.5, color=INK, lw=1.2)
ax_h.axvline(N_Z - 0.5, color=INK, lw=1.2)
# 점수에서 max로 묶은 쌍 강조
for a, b in MAX_PAIRS:
    for i, j in ((src.index(a), src.index(b)), (src.index(b), src.index(a))):
        ax_h.add_patch(Rectangle((j - 0.46, i - 0.46), 0.92, 0.92, fill=False, ec=INK, lw=2.2, zorder=3))
r_logon = raw.loc["다른 PC 로그온", "야간 로그온"]
r_send = raw.loc["회사계정 외부 발송", "회사계정 외부 첨부"]
fig.text(0.03, 0.072, "굵은 테두리 = 점수에서 큰 값 하나만 반영(max)하는 쌍  ·  구분선 왼쪽·위 = z-score형 6개, 오른쪽·아래 = 규칙형 2개",
         fontsize=9.5, color=INK, ha="left", va="bottom")
fig.text(0.03, 0.047, f"원건수 기준과 비교: 다른 PC ↔ 야간 로그온 {r_logon:.2f} → 평소 대비 z {corr.iloc[4, 5]:.2f}  ·  "
         f"외부 발송 ↔ 외부 첨부 {r_send:.2f} → {corr.iloc[0, 2]:.2f}",
         fontsize=9.5, color=INK, ha="left", va="bottom")
header(ax_h, "지표 간 상관 (점수 입력 기준)",
       "가장 높은 두 쌍도 0.57 · 0.50  →  두 쌍은 점수에서 큰 값 하나만 반영", x_off=-128)

# 컬러바
cax = fig.add_axes([0.61, 0.235, 0.012, 0.61])
cb = fig.colorbar(ax_h.images[0], cax=cax)
cb.outline.set_visible(False)
cb.ax.tick_params(labelsize=9, colors=MUTED, length=0)
cb.set_label("상관계수 (-1 반대 방향 · +1 같은 방향)", fontsize=9.5, color=MUTED)

# ── 오른쪽: VIF ──
y = np.arange(n)
ax_v.barh(y, vif_vals, height=0.62, color=[BAR_Z] * N_Z + [BAR_RULE] * (n - N_Z), zorder=2)
for yi, v in zip(y, vif_vals):
    ax_v.text(v + 0.08, yi, f"{v:.2f}", va="center", ha="left", fontsize=10.5, color=INK, zorder=3)
ax_v.axvline(1, color="#c9d0d7", lw=1, zorder=1)
ax_v.axvline(5, color=CUT_C, lw=1.6, ls=(0, (4, 3)), zorder=1)
ax_v.text(5.12, (n - 1) / 2, "검토 기준 5", color=CUT_C, fontsize=10, ha="left", va="center", rotation=90, fontweight="bold")
ax_v.set_xlim(0, 6)
ax_v.set_ylim(n - 0.5, -0.5)
ax_v.set_yticks(y, labels, fontsize=10.5, color=INK)
ax_v.set_xticks([0, 1, 2, 3, 4, 5, 6])
ax_v.set_xlabel("VIF = 1 ÷ (1 - R²)", fontsize=10.5, color=MUTED)
ax_v.tick_params(labelsize=10, colors=MUTED)
ax_v.tick_params(axis="y", length=0, colors=INK)
ax_v.grid(axis="x", color=GRID, lw=0.8, zorder=0)
for s in ("top", "right"):
    ax_v.spines[s].set_visible(False)
for s in ("left", "bottom"):
    ax_v.spines[s].set_color("#c9d0d7")
header(ax_v, "다중공선성 (VIF)", f"8개 모두 {min(vif_vals):.2f}~{max(vif_vals):.2f}  →  제외할 지표 없음", x_off=-118)

fig.text(0.03, 0.008,
         "상관: 점수 대상 308,023 사용자·일(2010-02~2011-05), Pearson, z-score형은 개인 기준선 z · 규칙형은 점수 발생 여부(0/1)  |  "
         "VIF: 보정 이후 225,281 사용자·일, 8개 입력을 함께 넣은 보조회귀\n"
         "정답 미사용  ·  상관·VIF가 낮다는 것은 선형 중복이 작다는 뜻이며, 탐지 성능을 뜻하지 않음",
         ha="left", va="bottom", fontsize=8.5, color=MUTED, linespacing=1.5)

fig.savefig(OUT / "06_지표중복_상관_VIF.png", dpi=150, facecolor="white")
fig.savefig(OUT / "06_지표중복_상관_VIF.svg", facecolor="white")
print("saved")
