"""규칙형 점수지표 2개의 분포: 평소 행동 vs 점수를 주는 구간 (1×2, PNG + SVG).

실행: 프로젝트 루트에서 python outputs/figures/발표자료/make_rule_indicators.py
- 구직 키워드: 회사 계정 메일 1통에 든 구직 키워드(12개 사전) 수. 3개 이상이면 구직 메일 → 2점.
  정의는 src/pipelines/email_user_day/build_email_user_day_dataset.py와 같음.
  email.csv 집계 결과는 05_규칙형_구직키워드_메일당분포.csv로 저장하고, 있으면 다시 씀.
- 새로운 야간 메일: 야간(19시~07시) 메일이 있는 점수 대상 사용자·일에서 직전 30활동일 중 야간 메일이 있던 날 수.
  0일이면 1점 (user_day_baseline_30.csv의 night_mail_flag, night_mail_past30).
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
KW_CSV = OUT / "05_규칙형_구직키워드_메일당분포.csv"

JOB_KEYWORDS = {"resume", "salary", "job", "opening", "benefits", "compensation", "part-time",
                "permanent", "career", "interview", "hiring", "position"}
JOB_MIN_WORDS = 3

INK, MUTED, GRID = "#1f2933", "#6b7785", "#eceff2"
POINT_C = {0: "#2f6db0", 1: "#f2b134", 2: "#e8772e", 3: "#c8323c"}
ZONE_C = {0: "#e3f1ee", 1: "#fdf0c8", 2: "#fbdcc2", 3: "#f6cdd0"}
NORMAL_BAR = "#2f6db0"


# ── 데이터 ──
def keyword_counts() -> pd.DataFrame:
    if KW_CSV.exists():
        return pd.read_csv(KW_CSV)
    ldap = pd.read_csv(ROOT / "inputs/LDAP/2009-12.csv", usecols=["user_id", "email"])
    corp_mail = dict(zip(ldap.user_id, ldap.email.str.lower()))
    counts = np.zeros(len(JOB_KEYWORDS) + 1, dtype=np.int64)
    for ch in pd.read_csv(ROOT / "inputs/events/email.csv", usecols=["user", "from", "content"],
                          dtype=str, chunksize=200_000):
        corp = ch["from"].fillna("").str.lower().to_numpy() == ch["user"].map(corp_mail).to_numpy()
        n = np.array([len(JOB_KEYWORDS & set(str(c).lower().split())) for c in ch["content"][corp]])
        counts += np.bincount(n, minlength=len(counts))
    df = pd.DataFrame({"keywords": np.arange(len(counts)), "mails": counts})
    df.to_csv(KW_CSV, index=False, encoding="utf-8-sig")
    return df


kw = keyword_counts()
total_mail = int(kw.mails.sum())
normal_mail = int(kw.loc[kw.keywords < JOB_MIN_WORDS, "mails"].sum())
job_mail = total_mail - normal_mail

b = pd.read_csv(ROOT / "outputs/datasets/생성지표/user_day_baseline_30.csv",
                usecols=["is_scored", "jobkw_mail_flag", "night_mail_flag", "night_mail_past30"])
b = b[b.is_scored.eq(1)]
n_rows = len(b)
job_days = int(b.jobkw_mail_flag.sum())
night = b[b.night_mail_flag.eq(1)]
n_night = len(night)
new_night = int(night.night_mail_past30.eq(0).sum())

# 야간 메일: 직전 30활동일 중 야간 메일이 있던 날 수 구간
bins = [(0, 0, "0일"), (1, 2, "1~2"), (3, 4, "3~4"), (5, 9, "5~9"), (10, 19, "10~19"), (20, 30, "20~30")]
past = night.night_mail_past30
night_bins = [int(past.between(lo, hi).sum()) for lo, hi, _ in bins]
assert sum(night_bins) == n_night, (sum(night_bins), n_night)

# ── 그림 ──
fig, axes = plt.subplots(1, 2, figsize=(16, 9), dpi=150)
fig.patch.set_facecolor("white")
fig.subplots_adjust(left=0.06, right=0.985, top=0.885, bottom=0.19, wspace=0.16)


def style(ax):
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.tick_params(labelsize=10.5, colors=MUTED)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c9d0d7")


def header(ax, title, tag, line):
    ax.annotate(title, (0, 1), xycoords="axes fraction", xytext=(0, 30), textcoords="offset points",
                ha="left", va="bottom", fontsize=17, fontweight="bold", color=INK)
    ax.annotate(tag, (1, 1), xycoords="axes fraction", xytext=(0, 33), textcoords="offset points",
                ha="right", va="bottom", fontsize=10, color=MUTED, family="Consolas")
    ax.annotate(line, (0, 1), xycoords="axes fraction", xytext=(0, 8), textcoords="offset points",
                ha="left", va="bottom", fontsize=12, fontweight="bold", color=INK)


def key_strip(ax, items):
    """패널 아래 점수 구간 표: [(점수, 설명, 비중), ...]"""
    w = 1 / len(items)
    for k, (pts, text, share) in enumerate(items):
        x0 = k * w
        ax.add_patch(Rectangle((x0 + 0.004, -0.2), w - 0.008, 0.07, transform=ax.transAxes, clip_on=False,
                               fc=ZONE_C[pts], ec=POINT_C[pts], lw=1.4 if pts else 0.9))
        ax.text(x0 + w / 2, -0.165, f"{pts}점  {text}  ·  {share}", transform=ax.transAxes, ha="center",
                va="center", fontsize=10.5, color=INK, fontweight="bold" if pts else "normal")


# 왼쪽: 구직 키워드 (메일 단위, 로그 축)
ax = axes[0]
shown = kw[kw.mails > 0]
x = shown.keywords.to_numpy()
y = shown.mails.to_numpy()
ax.axvspan(-0.6, JOB_MIN_WORDS - 0.5, color=ZONE_C[0], zorder=0, lw=0)
ax.axvspan(JOB_MIN_WORDS - 0.5, x.max() + 0.6, color=ZONE_C[2], zorder=0, lw=0)
ax.axvline(JOB_MIN_WORDS - 0.5, color=POINT_C[2], lw=1.6, ls=(0, (4, 3)), zorder=1)
ax.bar(x, y, width=0.72, color=[NORMAL_BAR if v < JOB_MIN_WORDS else POINT_C[2] for v in x], zorder=2)
for xi, yi in zip(x, y):
    ax.text(xi, yi * 1.35, f"{yi:,}", ha="center", va="bottom", fontsize=9.5, color=INK, zorder=3)
ax.set_yscale("log")
ax.yaxis.set_major_formatter(plt.FuncFormatter(
    lambda v, _: {1: "1", 10: "10", 100: "100", 1e3: "1천", 1e4: "1만", 1e5: "10만", 1e6: "100만"}.get(v, "")))
ax.set_ylim(0.7, y.max() * 12)
ax.set_xlim(-0.6, x.max() + 0.6)
ax.set_xticks(x)
ax.set_xlabel("회사 계정 메일 1통에 든 구직 키워드 수 (12개 사전 중)", fontsize=11, color=MUTED)
ax.set_ylabel("메일 수 (로그 눈금)", fontsize=11, color=MUTED)
style(ax)
ax.text(1, y.max() * 4, f"평소 범위\n0~2개 = {normal_mail / total_mail:.2%}", ha="center", va="center",
        fontsize=12, fontweight="bold", color="#0f6e62", zorder=3)
ax.text((JOB_MIN_WORDS - 0.5 + x.max() + 0.6) / 2, y.max() * 4,
        f"3개 이상 = {job_mail:,}통 ({job_mail / total_mail:.3%})\n→ 구직 메일 2점 (사용자·일 {job_days}일)",
        ha="center", va="center",
        fontsize=12, fontweight="bold", color="#b4531b", zorder=3)
header(ax, "구직 키워드 메일", "jobkw_mail_flag",
       f"대부분 0~2개에 몰려 있다가 3개부터 급감 → 그 구간을 2점으로")
key_strip(ax, [(0, "키워드 0~2개", f"{normal_mail / total_mail:.2%}"),
               (2, "키워드 3개 이상", f"{job_mail / total_mail:.3%}")])

# 오른쪽: 새로운 야간 메일 (야간 메일이 있는 날 단위)
ax = axes[1]
labels = [lab for *_, lab in bins]
xs = np.arange(len(bins))
ax.axvspan(-0.6, 0.5, color=ZONE_C[1], zorder=0, lw=0)
ax.axvspan(0.5, len(bins) - 0.4, color=ZONE_C[0], zorder=0, lw=0)
ax.axvline(0.5, color=POINT_C[1], lw=1.6, ls=(0, (4, 3)), zorder=1)
ax.bar(xs, night_bins, width=0.72, color=[POINT_C[1]] + [NORMAL_BAR] * (len(bins) - 1), zorder=2)
for xi, yi in zip(xs, night_bins):
    ax.text(xi, yi + max(night_bins) * 0.015, f"{yi:,}", ha="center", va="bottom", fontsize=10, color=INK, zorder=3)
ax.set_xticks(xs, labels)
ax.set_xlim(-0.6, len(bins) - 0.4)
ax.set_ylim(0, max(night_bins) * 1.3)
ax.set_xlabel("직전 30활동일 중 야간 메일이 있던 날 수", fontsize=11, color=MUTED)
ax.set_ylabel("야간 메일이 있는 사용자·일", fontsize=11, color=MUTED)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
style(ax)
habit = n_night - new_night
ax.text(0, max(night_bins) * 1.17, f"새로 나타난 날\n{new_night}일 ({new_night / n_night:.1%})\n→ 1점",
        ha="center", va="center", fontsize=11, fontweight="bold", color="#9a6a00", zorder=3)
ax.text((0.5 + len(bins) - 0.4) / 2, max(night_bins) * 1.17,
        f"평소에도 밤에 보내던 사람의 날\n{habit:,}일 ({habit / n_night:.1%}) → 0점",
        ha="center", va="center", fontsize=12, fontweight="bold", color="#0f6e62", zorder=3)
header(ax, "새로운 야간 메일", "night_mail_flag · night_mail_past30",
       f"야간 메일 {n_night:,}일 대부분은 늘 하던 행동 → 새로 나타난 날만 1점으로")
key_strip(ax, [(0, "직전 30일에 야간 메일 1일 이상", f"{habit / n_night:.1%}"),
               (1, "직전 30일 0일 (새로 나타남)", f"{new_night / n_night:.1%}")])

fig.text(0.5, 0.012,
         f"대상: 점수 대상 사용자·일 {n_rows:,}행 (구직 키워드 분포는 회사 계정 메일 {total_mail:,}통)  ·  "
         "야간 = 19시~07시  ·  정답 미사용  ·  구직 키워드 사전은 정답 메일을 보고 만들어졌을 위험이 있음",
         ha="center", va="bottom", fontsize=9, color=MUTED)

fig.savefig(OUT / "05_규칙형_2개_분포.png", dpi=150, facecolor="white")
fig.savefig(OUT / "05_규칙형_2개_분포.svg", facecolor="white")
print(f"corp mails {total_mail:,} · 0~2 {normal_mail:,} · 3+ {job_mail:,} · job days {job_days}")
print(f"night days {n_night:,} · new {new_night} · bins {dict(zip(labels, night_bins))}")
