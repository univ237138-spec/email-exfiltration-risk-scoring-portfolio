"""Deterministic email scoring. Labels are never read by this module."""
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

CORE = {
    "corp_ext_send_cnt": "회사 계정 외부 발송",
    "new_ext_rcpt_cnt": "신규 외부 수신자",
    "corp_ext_att_mail_cnt": "회사 계정 외부 첨부",
    "personal_att_mail_cnt": "개인 계정 첨부",
}
# int_rcpt_cnt (사내 수신자) removed 2026-09-21: weak domestic-case basis; see 사내수신자_제외실험/실험결과.md.
LOGON = {"other_pc_logon_cnt": "다른 PC 로그인", "night_logon_cnt": "야간 로그인"}
RULES = {"jobkw_mail": "구직 키워드 메일", "night_mail": "새로운 야간 메일"}
LABELS = CORE | RULES
GRADES = ["정상", "관심", "주의", "위험"]
COLORS = {"정상": "#4d9b92", "관심": "#e3b341", "주의": "#f28b50", "위험": "#f0677a", "기준선 부족": "#718096"}
VERSION = "email-review-v2.2"
# Logon alert (option 2, decided 2026-09-21): logon score 3, or score 2 with max logon z >= this cut.
# Fixed from the 2010-01~05 calibration period without labels so that email caution-or-logon alerts match
# the calibration rate of email caution-or-PC-time-link alerts (로그온채널_동일경보량비교/calibrate_option2.py).
LOGON_Z_CUT = 1.9443


@dataclass(frozen=True)
class Policy:
    job_points: int = 2
    night_points: int = 1
    # External-attachment mail is a subset of external-send mail. Keep both
    # indicators and their evidence, but count only the larger point value.
    overlap: str = "max"
    attention: int = 2
    caution: int = 3
    danger: int = 5
    logon_rule: str = "strict"

    def __post_init__(self):
        if self.overlap not in {"sum", "max"}:
            raise ValueError("overlap must be sum or max")
        if not 0 < self.attention < self.caution < self.danger:
            raise ValueError("등급 경계는 관심 < 주의 < 위험 순서여야 합니다.")
        if self.job_points not in (0, 1, 2, 3) or self.night_points not in (0, 1):
            raise ValueError("규칙 점수 범위를 확인하세요.")
        if self.logon_rule not in {"strict", "basic"}:
            raise ValueError("logon_rule must be strict or basic")

    def to_dict(self):
        return asdict(self)


def fit_thresholds(df):
    """Freeze quantiles from eligible Jan–May 2010 rows only."""
    normal = df[df.is_scored.eq(1) & df.date.between("2010-01-01", "2010-05-31")]
    if normal.empty:
        raise ValueError("보정 기간(2010-01~05)의 점수 대상 데이터가 없습니다.")
    return {c: normal[c + "_z"].quantile([.99, .9975, .9995]).tolist() for c in CORE | LOGON}


def points(z, thresholds):
    if len(thresholds) != 3 or not np.isfinite(thresholds).all() or not np.all(np.diff(thresholds) >= 0):
        raise ValueError("유효하지 않은 점수 경계입니다.")
    return sum((z >= t).astype("int8") for t in thresholds).astype("int8")


def score(df, thresholds, policy=Policy()):
    out = df.copy()
    eligible = out.is_scored.eq(1)
    required = [c + "_z" for c in CORE | LOGON] + ["jobkw_mail_flag", "night_mail_flag", "night_mail_past30"]
    if not np.isfinite(out.loc[eligible, required].to_numpy(dtype=float)).all():
        raise ValueError("점수 대상 행에 지표 누락 또는 무한대 값이 있습니다.")
    for c in CORE | LOGON:
        out[c + "_points"] = points(out[c + "_z"], thresholds[c]).where(eligible).astype("Int64")
    out["jobkw_mail_points"] = (out.jobkw_mail_flag.eq(1) * policy.job_points).where(eligible).astype("Int64")
    novel_night = out.night_mail_flag.eq(1) & out.night_mail_past30.eq(0)
    out["night_mail_points"] = (novel_night * policy.night_points).where(eligible).astype("Int64")
    overlap = out[["corp_ext_send_cnt_points", "corp_ext_att_mail_cnt_points"]].min(axis=1)
    out["overlap_discount"] = (overlap if policy.overlap == "max" else pd.Series(0, index=out.index)).where(eligible).astype("Int64")
    cols = [c + "_points" for c in LABELS]
    out["total_score"] = (out[cols].sum(axis=1) - out.overlap_discount).where(eligible).astype("Int64")
    # Correlated login indicators use a maximum and never affect email grades.
    out["logon_score"] = out[[c + "_points" for c in LOGON]].max(axis=1).where(eligible).astype("Int64")
    s = out.total_score.fillna(-1).to_numpy(dtype=int)
    out["risk_grade"] = np.select([s >= policy.danger, s >= policy.caution, s >= policy.attention, eligible],
                                  ["위험", "주의", "관심", "정상"], default="기준선 부족")
    out["period_type"] = np.where(out.date <= pd.Timestamp("2010-05-31"), "보정기간 · 사후분석", "보정 이후")
    values = out[cols].fillna(0).to_numpy(dtype=int)
    lead = values.argmax(axis=1)
    out["top_reason"] = "점수 발생 지표 없음"
    for i, (c, label) in enumerate(LABELS.items()):
        mask = (lead == i) & (values.max(axis=1) > 0)
        if c in CORE:
            reason = (label + " " + out[c].astype(str) + "건 · 평소 " + out[c + "_mu"].round(2).astype(str)
                      + " · z " + out[c + "_z"].round(2).astype(str))
        else:
            reason = pd.Series(label + (" 발생" if c == "jobkw_mail" else " · 직전 30활동일 발생 0일"), index=out.index)
        out.loc[mask, "top_reason"] = reason.loc[mask] + " (+" + out.loc[mask, c + "_points"].astype(str) + ")"
    out.loc[~eligible, "top_reason"] = "과거 활동일 10일 / 첫 활동 후 30일 조건 미충족"
    add_logon_channel(out, eligible, policy)
    return out


def add_logon_channel(out, eligible, policy):
    """Separate logon alert channel; combined with email only in the review list, never in total_score."""
    ls = out.logon_score.fillna(0).to_numpy(dtype=int)
    maxz = out[[c + "_z" for c in LOGON]].max(axis=1).to_numpy(dtype=float)
    strong = (ls >= 2) if policy.logon_rule == "basic" else ((ls == 3) | ((ls == 2) & (maxz >= LOGON_Z_CUT)))
    el = eligible.to_numpy()
    out["logon_grade"] = np.select([~el, ls == 3, strong, ls >= 1], ["기준선 부족", "위험", "주의", "관심"], default="정상")
    out["logon_alert"] = out.logon_grade.isin(["주의", "위험"])
    email_alert = out.total_score.fillna(-1).ge(policy.caution).to_numpy()
    logon_alert = out.logon_alert.to_numpy()
    out["review_target"] = email_alert | logon_alert
    out["alert_channel"] = np.select([email_alert & logon_alert, email_alert, logon_alert], ["둘 다", "이메일", "로그온"], default="")
    parts = {c: (label + " " + out[c].astype(str) + "건 · 평소 " + out[c + "_mu"].round(2).astype(str)
                 + " · z " + out[c + "_z"].round(2).astype(str) + " (+" + out[c + "_points"].astype(str) + ")")
             for c, label in LOGON.items()}
    a, b = (out[c + "_points"].fillna(0).to_numpy(dtype=int) for c in LOGON)
    first, second = LOGON
    # Equal points: score stays the single value, but both indicators are shown as the reason.
    out["logon_reason"] = np.select([ls == 0, a == b, a > b],
                                    ["", parts[first] + " + " + parts[second] + " · 동시 발생", parts[first]], default=parts[second])
    out.loc[~eligible, "logon_reason"] = ""


def alert_rates(df, policy=Policy()):
    s = df.loc[df.is_scored.eq(1), "total_score"]
    return pd.DataFrame({
        "등급": ["관심 이상", "주의 이상", "위험"],
        "기준 점수": [policy.attention, policy.caution, policy.danger],
        "목표 비율(%)": [1.39, .36, .07],
        "실제 비율(%)": [float(s.ge(t).mean() * 100) if len(s) else 0. for t in [policy.attention, policy.caution, policy.danger]],
        "사용자·일": [int(s.ge(t).sum()) for t in [policy.attention, policy.caution, policy.danger]],
    })


def channel_rates(df):
    s = df[df.is_scored.eq(1)]
    n = len(s)
    rows = [("이메일 주의 이상", s.alert_channel.isin(["이메일", "둘 다"])), ("로그온 경보", s.logon_alert),
            ("조사 대상 (이메일 또는 로그온)", s.review_target)]
    return pd.DataFrame({"구분": [r[0] for r in rows],
                         "비율(%)": [float(m.mean() * 100) if n else 0. for _, m in rows],
                         "사용자·일": [int(m.sum()) for _, m in rows]})


def evidence(row, thresholds):
    rows = []
    for c, label in CORE.items():
        rows.append({"행동지표": label, "오늘": float(row[c]), "평소 평균": float(row[c + "_mu"]),
                     "z": float(row[c + "_z"]), "점수": row[c + "_points"],
                     "점수 기준": " / ".join(f"{v:.3f}" for v in thresholds[c])})
    for c, label in RULES.items():
        rows.append({"행동지표": label, "오늘": float(row[c + "_cnt"]), "평소 평균": None, "z": None,
                     "점수": row[c + "_points"], "점수 기준": "발생 시 규칙 점수" if c == "jobkw_mail" else f"과거 발생 {row[c + '_past30']:g}일 · 0일일 때만"})
    return pd.DataFrame(rows)
