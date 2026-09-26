"""z-score 점수지표 6개의 실제 사례 (2×3, PNG + SVG + 선택 사례 CSV).

실행: 프로젝트 루트에서 python outputs/figures/발표자료/make_zscore_cases.py

사례 선택 규칙 (6개 지표 공통, 결과를 보기 전에 고정):
  - 보정기간(metadata.json의 normal_period_end까지) 점수 대상 행
  - 해당 지표 점수가 정확히 2점인 날
  - 기준선이 30활동일로 모두 찬 날 (base_n == 30)
  - r4.2 정답 내부자 70명은 후보에서 제외 (탐지 성공 사례로 보이지 않도록)
  - 남은 후보 중 시드 20260924로 무작위 1건
점수 구간 띠 = 그날의 평소 평균 + k점 z 경계 × max(표준편차, 1) (k = 1, 2, 3). 점수 경계는 대시보드 metadata.json 값.
각 패널 아래에는 지표별 z 경계를 같은 색의 표로 표시.
"""
import json
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SEED = 20260924
BEFORE, AFTER = 30, 5

INDICATORS = [
    ("corp_ext_send_cnt", "회사 계정 외부 발송", "메일 수"),
    ("new_ext_rcpt_cnt", "신규 외부 수신자", "주소 수"),
    ("corp_ext_att_mail_cnt", "회사 계정 외부 첨부", "메일 수"),
    ("personal_att_mail_cnt", "개인 계정 첨부", "메일 수"),
    ("other_pc_logon_cnt", "다른 PC 로그온", "로그온 수"),
    ("night_logon_cnt", "야간 로그온", "로그온 수"),
]

INK, MUTED, GRID = "#1f2933", "#6b7785", "#eceff2"
BASE_C, BAND_C, CUT_C, LINE_C = "#0f8a7a", "#e3f1ee", "#7b8794", "#9fb3c8"
POINT_C = {0: "#2f6db0", 1: "#f2b134", 2: "#e8772e", 3: "#c8323c"}
ZONE_C = {0: "#e3f1ee", 1: "#fdf0c8", 2: "#fbdcc2", 3: "#f6cdd0"}  # 점수 구간 띠 (0점 = 평소 범위)

meta = json.loads((ROOT / "outputs/dashboard/metadata.json").read_text(encoding="utf-8"))
CUTS = meta["thresholds"]
CAL_END = pd.Timestamp(meta["normal_period_end"])

cols = ["user", "date", "is_scored", "base_n"]
for c, *_ in INDICATORS:
    cols += [c, f"{c}_mu", f"{c}_sd", f"{c}_z"]
df = pd.read_csv(ROOT / "outputs/datasets/생성지표/user_day_baseline_30.csv", usecols=cols, parse_dates=["date"])
df = df.sort_values(["user", "date"]).reset_index(drop=True)

ins = pd.read_csv(ROOT / "labels/answers/insiders.csv", dtype=str)
insiders = set(ins.loc[ins["dataset"].astype(float).eq(4.2), "user"])
assert len(insiders) == 70, len(insiders)


def points(z, cuts):
    return sum((z >= t).astype(int) for t in cuts)


rng = np.random.default_rng(SEED)
picked = []
for c, name, unit in INDICATORS:
    pts = points(df[f"{c}_z"], CUTS[c])
    cand = df[df.is_scored.eq(1) & df.date.le(CAL_END) & df.base_n.eq(30)
              & pts.eq(2) & ~df.user.isin(insiders)]
    row = cand.iloc[rng.integers(len(cand))]
    picked.append((c, name, unit, row.name, len(cand)))

fig, axes = plt.subplots(2, 3, figsize=(16, 9), dpi=150)
fig.patch.set_facecolor("white")
fig.subplots_adjust(left=0.04, right=0.99, top=0.94, bottom=0.15, hspace=0.5, wspace=0.12)

records = []
for ax, (c, name, unit, idx, n_cand) in zip(axes.flat, picked):
    user = df.at[idx, "user"]
    u = df.index[df.user.eq(user)]
    pos = u.get_loc(idx)
    w = df.loc[u[max(0, pos - BEFORE): pos + AFTER + 1]].copy()
    w = w[w[f"{c}_mu"].notna()]  # 기준선이 아직 없는 초기 날짜는 표시하지 않음
    cuts = CUTS[c]
    sd_f = np.maximum(w[f"{c}_sd"], 1)
    for k in range(3):
        w[f"cut{k + 1}"] = w[f"{c}_mu"] + cuts[k] * sd_f
    w["pts"] = points(w[f"{c}_z"], cuts).where(w[f"{c}_z"].notna(), 0)
    ymax = max(w[c].max(), w.cut3.max()) * 1.12 + 0.3

    # 점수 구간 띠: 그날의 평균 + z경계 × max(표준편차, 1)
    edges = [np.zeros(len(w)), w.cut1, w.cut2, w.cut3, np.full(len(w), ymax)]
    for k in range(4):
        ax.fill_between(w.date, edges[k], edges[k + 1], color=ZONE_C[k], lw=0, zorder=0)
    for k in (1, 2, 3):
        ax.plot(w.date, w[f"cut{k}"], color=POINT_C[k], lw=0.7, alpha=0.7, zorder=1)
    ax.plot(w.date, w[f"{c}_mu"], color=BASE_C, lw=2.2, zorder=2)
    ax.plot(w.date, w[c], color=LINE_C, lw=1.0, zorder=3)
    for p, g in w.groupby("pts"):
        ax.scatter(g.date, g[c], s=22 if p == 0 else 42, color=POINT_C[int(p)], zorder=4,
                   edgecolor="white", linewidth=0.6, clip_on=False)

    sel = df.loc[idx]
    sel_date = pd.Timestamp(sel["date"])
    ax.axvspan(mdates.date2num(sel_date - pd.Timedelta(hours=14)), mdates.date2num(sel_date + pd.Timedelta(hours=14)), color="#fbe3d4", zorder=-1)
    ax.scatter([sel_date], [sel[c]], s=150, color=POINT_C[2], edgecolor=INK, linewidth=1.2, zorder=5, clip_on=False)

    ax.set_ylim(0, ymax)
    ax.set_xlim(w.date.min(), w.date.max())
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True, nbins=5))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.tick_params(labelsize=9, colors=MUTED)
    ax.grid(axis="y", color=GRID, lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c9d0d7")
    ax.set_ylabel(unit, fontsize=9.5, color=MUTED)

    # 제목 · 사용자/날짜 · 계산식은 축 위에 포인트 단위로 고정 배치 (축 크기와 무관)
    mu, sd, z = sel[f"{c}_mu"], sel[f"{c}_sd"], sel[f"{c}_z"]
    ax.annotate(name, (0, 1), xycoords="axes fraction", xytext=(0, 22), textcoords="offset points",
                ha="left", va="bottom", fontsize=14, fontweight="bold", color=INK)
    ax.annotate(f"{user} · {sel_date:%Y-%m-%d}", (1, 1), xycoords="axes fraction", xytext=(0, 24),
                textcoords="offset points", ha="right", va="bottom", fontsize=9.5, color=MUTED)
    ax.annotate(f"오늘 {int(sel[c])} · 평소 {mu:.2f} · 표준편차 {sd:.2f}  →  z {z:.2f}  →  2점", (0, 1),
                xycoords="axes fraction", xytext=(0, 5), textcoords="offset points",
                ha="left", va="bottom", fontsize=10.5, fontweight="bold", color=INK)

    labels = [f"0점  z < {cuts[0]:.2f}", f"1점  {cuts[0]:.2f} ~ {cuts[1]:.2f}",
              f"2점  {cuts[1]:.2f} ~ {cuts[2]:.2f}", f"3점  z ≥ {cuts[2]:.2f}"]
    for k, text in enumerate(labels):
        x0 = k / 4
        ax.add_patch(Rectangle((x0 + 0.004, -0.215), 0.242, 0.1, transform=ax.transAxes, clip_on=False,
                               fc=ZONE_C[k], ec=POINT_C[k], lw=1.4 if k == 2 else 0.8))
        ax.text(x0 + 0.125, -0.165, text, transform=ax.transAxes, ha="center", va="center",
                fontsize=8.8, color=INK, fontweight="bold" if k == 2 else "normal")

    records.append(dict(indicator=c, name=name, user=user, date=sel.date.date(), value=int(sel[c]),
                        baseline_mean=round(mu, 4), baseline_sd=round(sd, 4), z=round(z, 4),
                        cut1=cuts[0], cut2=cuts[1], cut3=cuts[2], candidates=n_cand, seed=SEED))

handles = [
    Line2D([], [], color=BASE_C, lw=2.2, label="평소 (직전 30활동일 평균)"),
    Line2D([], [], color=LINE_C, lw=1, marker="o", mfc=POINT_C[0], mec="white", ms=6, label="그날 관측값 (점 색 = 받은 점수)"),
    Patch(fc=ZONE_C[0], ec=BASE_C, lw=0.8, label="0점 · 평소 범위"),
    Patch(fc=ZONE_C[1], ec=POINT_C[1], lw=0.8, label="1점"),
    Patch(fc=ZONE_C[2], ec=POINT_C[2], lw=0.8, label="2점"),
    Patch(fc=ZONE_C[3], ec=POINT_C[3], lw=0.8, label="3점"),
]
fig.legend(handles=handles, loc="lower center", ncol=6, frameon=False, fontsize=10,
           bbox_to_anchor=(0.5, 0.036), handletextpad=0.5, columnspacing=1.8)
fig.text(0.5, 0.004,
         "구간 경계 = 그날 평균 + z경계 × max(표준편차, 1)  ·  표시 구간: 직전 30활동일 + 이후 5활동일\n"
         f"사례 선택 (6개 지표 공통): 보정기간(2010-02~05)에 해당 지표 2점인 날 · 기준선 30활동일 충족 · 정답 내부자 70명 제외 · "
         f"시드 {SEED} 무작위 1건  ·  작동 방식 예시이며 대표성·탐지 성공을 뜻하지 않음",
         ha="center", va="bottom", fontsize=8, color=MUTED, linespacing=1.5)

fig.savefig(OUT / "04_z지표_6개_실제사례.png", dpi=150, facecolor="white")
fig.savefig(OUT / "04_z지표_6개_실제사례.svg", facecolor="white")
pd.DataFrame(records).to_csv(OUT / "04_z지표_6개_실제사례_선택.csv", index=False, encoding="utf-8-sig")
print(pd.DataFrame(records).to_string(index=False))
