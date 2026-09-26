"""직무 보정 강도 w별 의심사용자 순위 (정답 미사용). v3와 달라지는 곳은 기대 경보율 한 줄뿐.
기대 경보율 = 직무 평균^w × 전체 평균^(1-w)
실행: 작업공간 루트에서 python experiments/20260922_직무보정_분할검증/rank_w.py
"""
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import numpy as np
import pandas as pd
from scipy.stats import poisson

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = PROJECT_ROOT / "outputs/dashboard/email_user_day_scores.csv"
START, WINDOW, MIN_PEERS = "2010-06-01", 30, 5
WS = [0, 0.25, 0.5, 0.75, 1]

d = pd.read_csv(SRC, usecols=["user", "date", "total_score", "logon_score", "logon_alert"], encoding="utf-8-sig",
                parse_dates=["date"])
d = d[(d.date >= START) & d.total_score.notna()].copy()
d = d.merge(pd.read_csv(PROJECT_ROOT / "inputs/LDAP/2009-12.csv", usecols=["user_id", "role"]).rename(columns={"user_id": "user"}),
            on="user", how="left")
d["email"] = d.total_score >= 3
d["logon"] = d.logon_alert.astype(bool)
per = d.groupby("user").agg(role=("role", "first"), days=("date", "size"), email=("email", "sum"), logon=("logon", "sum"))
role_sum, role_n, glob = per.groupby("role")[["days", "email", "logon"]].sum(), per.groupby("role").size(), per[["days", "email", "logon"]].sum()

def rates(u, ch):
    """(직무 평균, 전체 평균, 동료 5명 이상 여부). 둘 다 본인 제외, 가상 경보 1건 포함 (v3와 동일)."""
    r = per.loc[u]
    g_rate = glob[ch] / glob["days"]
    ga, gd = glob[ch] - r[ch], glob["days"] - r["days"]
    glob_rate = (ga + 1) / (gd + 1 / g_rate)
    if role_n[r.role] - 1 >= MIN_PEERS:
        s = role_sum.loc[r.role]
        return (s[ch] - r[ch] + 1) / (s["days"] - r["days"] + 1 / g_rate), glob_rate, True
    return glob_rate, glob_rate, False

# 채널별 최대 30일 창은 w와 무관하므로 한 번만 계산
win = []
for u, g in d.groupby("user", sort=False):
    g = g.sort_values("date")
    r = {"user": u, "role": g.role.iloc[0], "max_email_score": int(g.total_score.max()), "max_logon_score": int(g.logon_score.max())}
    for ch in ["email", "logon"]:
        a = g.loc[g[ch], "date"].to_numpy()
        if not len(a):
            continue
        best, ws = 0, a[0]
        for t in a:
            k = int(((a >= t) & (a < t + np.timedelta64(WINDOW, "D"))).sum())
            if k > best:
                best, ws = k, t
        in_w = (g.date >= ws) & (g.date <= ws + np.timedelta64(WINDOW - 1, "D"))
        r[f"{ch}_k"], r[f"{ch}_n"] = best, int(in_w.sum())
        r[f"{ch}_role_rate"], r[f"{ch}_glob_rate"], r[f"{ch}_peer"] = rates(u, ch)
    win.append(r)
win = pd.DataFrame(win)

def rank(w):
    u = win.copy()
    for ch in ["email", "logon"]:
        has = u[f"{ch}_k"].notna()
        rate = np.where(u[f"{ch}_peer"].astype("boolean").fillna(False).to_numpy(bool),
                        u[f"{ch}_role_rate"] ** w * u[f"{ch}_glob_rate"] ** (1 - w), u[f"{ch}_glob_rate"])
        lam = rate * u[f"{ch}_n"]
        u[f"{ch}_p"] = np.where(has, poisson.sf(u[f"{ch}_k"].fillna(1) - 1, np.where(has, lam, 1.0)), 1.0)
    u["p"] = u[["email_p", "logon_p"]].min(axis=1)
    u["surprise"] = -np.log10(u.p.clip(lower=1e-300))
    has_any = u.email_k.notna() | u.logon_k.notna()
    u["priority"] = np.select([u.p < 1e-4, u.p < 1e-3, has_any], ["1순위", "2순위", "관찰"], "해당 없음")
    u = u.sort_values(["surprise", "max_email_score", "max_logon_score"], ascending=False).reset_index(drop=True)
    u.insert(0, "rank", u.index + 1)
    return u[["rank", "user", "role", "priority", "surprise", "p", "email_p", "logon_p", "email_k", "logon_k",
              "max_email_score", "max_logon_score"]]

if __name__ == "__main__":
    for w in WS:
        rank(w).to_csv(HERE / f"순위_w{w}.csv", index=False, encoding="utf-8-sig")
    v3 = pd.read_csv(HERE.parent / "20260922_내부자탐지_정답미사용/의심사용자_순위.csv", encoding="utf-8-sig")
    r1 = pd.read_csv(HERE / "순위_w1.csv", encoding="utf-8-sig")
    same_order = (v3.user.tolist() == r1.user.tolist())
    max_dp = float((v3.set_index("user").surprise - r1.set_index("user").surprise).abs().max())
    print(f"w=1 과 v3 비교: 순서 동일 {same_order}, surprise 최대 차이 {max_dp:.2e}")
    for w in WS:
        t = pd.read_csv(HERE / f"순위_w{w}.csv", encoding="utf-8-sig")
        print(f"w={w}: 1·2순위 {int(t.priority.isin(['1순위','2순위']).sum())}명, 상위 25명 중 ITAdmin {int((t.head(25).role=='ITAdmin').sum())}명")
