"""보정 z-score 적용 지표 4개의 실제 분포 시각화.

실행: python src/pipelines/email_user_day/visualize_corrected_zscore.py  (data 폴더에서 실행)
출력: outputs/figures/행동지표/fig1_daily_value_distribution.png
      outputs/figures/행동지표/fig2_baseline_sigma_distribution.png
      outputs/figures/행동지표/fig3_zscore_before_after.png
"""
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import matplotlib
import matplotlib.ticker
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent

COMPETITOR = {"raytheon.com", "northropgrumman.com", "harris.com", "hp.com", "lockheedmartin.com", "boeing.com"}
WINDOW, MIN_PERIODS, WARMUP_DAYS = 30, 10, 30
SIGMA_FLOOR, Z_CAP, Z_ALERT = 1.0, 5.0, 3.0

INDICATORS = {
    "corp_ext_send_cnt": "회사 계정 → 외부 메일 수",
    "new_ext_rcpt_cnt": "신규 외부 수신자 수",
    "corp_ext_att_mail_cnt": "회사 계정 → 외부 첨부 메일 수",
    "personal_att_mail_cnt": "개인 계정 첨부 메일 수",
}

# 색상: 참조 팔레트 categorical slot 1(보정 후), slot 2(보정 전), 텍스트·축은 중립색
C_AFTER, C_BEFORE = "#2a78d6", "#eb6834"
C_TEXT, C_MUTED, C_GRID, C_SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"

plt.rcParams.update({
    "font.family": "Malgun Gothic",
    "axes.unicode_minus": False,
    "figure.facecolor": C_SURFACE,
    "axes.facecolor": C_SURFACE,
    "axes.edgecolor": C_GRID,
    "axes.labelcolor": C_MUTED,
    "xtick.color": C_MUTED,
    "ytick.color": C_MUTED,
    "axes.grid": True,
    "grid.color": C_GRID,
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 10,
})


def build_user_day() -> pd.DataFrame:
    """이메일 로그 → 사용자×날짜 지표 4개 (logon 활동일 기준, 메일 없는 날은 0)."""
    e = pd.read_csv(PROJECT_ROOT / "inputs/events/email.csv", usecols=["date", "user", "to", "cc", "bcc", "from", "attachments"], dtype=str)
    ldap = pd.read_csv(PROJECT_ROOT / "inputs/LDAP/2009-12.csv", usecols=["user_id", "email"])
    e = e.merge(ldap.rename(columns={"user_id": "user", "email": "ldap"}), on="user", how="left")

    low = lambda c: e[c].fillna("").str.lower()
    corp = (low("from") == e["ldap"].str.lower()).to_numpy()
    recipients = low("to") + ";" + low("cc") + ";" + low("bcc")
    ext = [{a for a in r.split(";") if a and not a.endswith("@dtaa.com")} for r in recipients]
    has_ext = np.array([len(x) > 0 for x in ext])
    has_att = e["attachments"].astype(int).to_numpy() > 0

    e["day"] = pd.to_datetime(e["date"], format="%m/%d/%Y %H:%M:%S").dt.normalize()
    e["corp_ext_send_cnt"] = corp & has_ext
    e["corp_ext_att_mail_cnt"] = corp & has_ext & has_att
    e["personal_att_mail_cnt"] = ~corp & has_att
    e["ext"] = ext
    daily = e.groupby(["user", "day"])[["corp_ext_send_cnt", "corp_ext_att_mail_cnt", "personal_att_mail_cnt"]].sum()

    # 신규 외부 수신자: 사용자별로 해당 주소가 처음 등장한 날짜에만 1회 집계 (과거 날짜 기준)
    first_seen = e[["user", "day", "ext"]].explode("ext").dropna().groupby(["user", "ext"])["day"].min()
    new_rcpt = first_seen.reset_index().groupby(["user", "day"]).size().rename("new_ext_rcpt_cnt")

    logon = pd.read_csv(PROJECT_ROOT / "inputs/events/logon.csv", usecols=["date", "user"])
    logon["day"] = pd.to_datetime(logon["date"], format="%m/%d/%Y %H:%M:%S").dt.normalize()
    grid = logon[["user", "day"]].drop_duplicates().set_index(["user", "day"]).sort_index()

    out = grid.join(daily, how="left").join(new_rcpt, how="left").fillna(0).astype(int)
    first_day = out.reset_index().groupby("user")["day"].transform("min")
    out["age_days"] = (out.index.get_level_values("day") - first_day.to_numpy()).days
    return out


def add_zscores(df: pd.DataFrame) -> pd.DataFrame:
    """지표별 과거 30일 기준선(당일 제외)과 보정 전·후 z-score."""
    for col in INDICATORS:
        grp = df[col].groupby(level="user")
        mu = grp.transform(lambda s: s.shift(1).rolling(WINDOW, min_periods=MIN_PERIODS).mean())
        sd = grp.transform(lambda s: s.shift(1).rolling(WINDOW, min_periods=MIN_PERIODS).std())
        df[f"{col}__mu"] = mu
        df[f"{col}__sd"] = sd
        df[f"{col}__z_raw"] = (df[col] - mu) / sd.replace(0, np.nan)
        df[f"{col}__z_adj"] = (df[col] - mu) / np.maximum(sd, SIGMA_FLOOR)
    return df


def style_title(fig, title, subtitle):
    fig.text(0.01, 0.985, title, fontsize=14, fontweight="bold", color=C_TEXT, va="top")
    fig.text(0.01, 0.945, subtitle, fontsize=10, color=C_MUTED, va="top")


def fig_daily_values(df):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for ax, (col, name) in zip(axes.flat, INDICATORS.items()):
        s = df[col]
        cap = 8
        vals = s.clip(upper=cap).value_counts(normalize=True).sort_index()
        labels = [str(v) if v < cap else f"{cap}+" for v in vals.index]
        ax.bar(labels, vals.values * 100, color=C_AFTER, width=0.7, edgecolor=C_SURFACE, linewidth=2)
        zero = (s == 0).mean() * 100
        ax.set_title(f"{name}\n{col}", fontsize=11, color=C_TEXT, loc="left")
        ax.text(0.98, 0.95, f"0인 날 {zero:.1f}%\n평균 {s.mean():.2f}  ·  p95 {s.quantile(.95):.0f}  ·  최대 {s.max()}",
                transform=ax.transAxes, ha="right", va="top", fontsize=9, color=C_MUTED)
        ax.text(0, vals.iloc[0] * 100, f"{vals.iloc[0]*100:.1f}%", ha="center", va="bottom", fontsize=9, color=C_TEXT)
        ax.set_xlabel("하루 값 (건·명)")
        ax.set_ylabel("사용자×날짜 비율 (%)")
        ax.grid(axis="x", visible=False)
    style_title(fig, "① 하루 값 분포: 4개 지표 모두 0이 67~88%",
                f"logon 활동일 기준 사용자×날짜 {len(df):,}개, 메일이 없는 날은 0으로 채움")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(OUT / "fig1_daily_value_distribution.png", dpi=150)
    plt.close(fig)


def fig_sigma(df):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for ax, (col, name) in zip(axes.flat, INDICATORS.items()):
        v = df[f"{col}__mu"].notna() & (df["age_days"] >= WARMUP_DAYS)
        sd = df.loc[v, f"{col}__sd"]
        bins = np.arange(0, 2.05, 0.05)
        w = np.ones(len(sd)) / len(sd) * 100
        ax.hist(sd.clip(upper=2), bins=bins, weights=w, color=C_AFTER, edgecolor=C_SURFACE, linewidth=0.8)
        ax.axvline(SIGMA_FLOOR, color=C_TEXT, linestyle="--", linewidth=1.2)
        zero, below = (sd == 0).mean() * 100, (sd < SIGMA_FLOOR).mean() * 100
        ax.text(SIGMA_FLOOR + 0.03, 0.95, f"σ 하한 1\n(왼쪽은 분모를 1로 대체)", transform=ax.get_xaxis_transform(),
                fontsize=9, color=C_TEXT, va="top")
        ax.text(0.98, 0.62, f"σ = 0: {zero:.1f}%\nσ < 1: {below:.1f}%", transform=ax.transAxes,
                ha="right", va="top", fontsize=10, color=C_TEXT, fontweight="bold")
        ax.set_title(f"{name}\n{col}", fontsize=11, color=C_TEXT, loc="left")
        ax.set_xlabel("과거 30일 기준선 표준편차 σ (2 이상은 2에 합침)")
        ax.set_ylabel("기준선 비율 (%)")
        ax.grid(axis="x", visible=False)
    style_title(fig, "② 기준선 σ 분포: 대부분 1보다 작아 하한이 적용됨",
                f"당일 제외 과거 {WINDOW}일, 최소 {MIN_PERIODS}일 기록, 사용자별 첫 {WARMUP_DAYS}일 제외")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(OUT / "fig2_baseline_sigma_distribution.png", dpi=150)
    plt.close(fig)


def fig_z(df):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5))
    bins = np.arange(-3, 12.25, 0.25)
    summary = []
    for ax, (col, name) in zip(axes.flat, INDICATORS.items()):
        v = df[f"{col}__mu"].notna() & (df["age_days"] >= WARMUP_DAYS)
        n = v.sum()
        z_raw = df.loc[v, f"{col}__z_raw"]
        z_adj = df.loc[v, f"{col}__z_adj"]
        undefined = z_raw.isna().mean() * 100
        for z, color, label in [(z_raw.dropna(), C_BEFORE, "보정 전 z = (x-μ)/σ"),
                                (z_adj, C_AFTER, "보정 후 z = (x-μ)/max(σ,1)")]:
            ax.hist(z.clip(-3, 12), bins=bins, weights=np.ones(len(z)) / n * 100,
                    histtype="step", linewidth=2, color=color, label=label)
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda y, _: f"{y:g}%"))
        ax.axvline(Z_ALERT, color=C_MUTED, linestyle="--", linewidth=1)
        ax.axvline(Z_CAP, color=C_MUTED, linestyle=":", linewidth=1)
        ax.text(Z_ALERT + 0.1, 0.97, "z = 3", transform=ax.get_xaxis_transform(), fontsize=9, color=C_MUTED, va="top")
        ax.text(Z_CAP + 0.1, 0.97, "상한 5", transform=ax.get_xaxis_transform(), fontsize=9, color=C_MUTED, va="top")
        before, after = (z_raw > Z_ALERT).sum() / n * 100, (z_adj > Z_ALERT).mean() * 100
        ax.text(0.98, 0.80, f"z > 3인 날\n보정 전 {before:.2f}%  →  보정 후 {after:.2f}%\n보정 전 계산 불가(σ=0) {undefined:.1f}%",
                transform=ax.transAxes, ha="right", va="top", fontsize=9, color=C_TEXT,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=C_SURFACE, edgecolor=C_GRID))
        ax.set_title(f"{name}\n{col}", fontsize=11, color=C_TEXT, loc="left")
        ax.set_xlabel("z-score (-3 미만·12 초과는 끝 구간에 합침)")
        ax.set_ylabel("사용자×날짜 비율 (%, 로그 척도)")
        ax.grid(axis="x", visible=False)
        summary.append((col, n, undefined, before, after))
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", bbox_to_anchor=(0.99, 0.99), frameon=False, ncol=2, fontsize=10)
    style_title(fig, "③ z-score 분포: 보정 후 1건 차이로 생기는 긴 꼬리가 사라짐",
                "보정 전은 σ = 0인 날을 계산할 수 없어 제외 (비율 분모는 기준선이 있는 전체 날)")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(OUT / "fig3_zscore_before_after.png", dpi=150)
    plt.close(fig)
    return summary


if __name__ == "__main__":
    df = add_zscores(build_user_day())
    fig_daily_values(df)
    fig_sigma(df)
    for col, n, undef, before, after in fig_z(df):
        print(f"{col:24s} n={n:,}  σ=0 {undef:5.1f}%  z>3 before {before:.2f}%  after {after:.2f}%")
    print("saved to", OUT)
