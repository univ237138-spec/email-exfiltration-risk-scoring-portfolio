"""Build reproducible local artifacts without changing source CSVs."""
import json
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import pandas as pd
import numpy as np
from scoring import CORE, LOGON, LABELS, VERSION, LOGON_Z_CUT, Policy, fit_thresholds, score, alert_rates, channel_rates
from linking import LOGON_CSV, EMAIL_CSV, WINDOW_MIN, CONTEXT_DAYS, load_link_events, link_context

HERE = Path(__file__).resolve().parent
SOURCE = PROJECT_ROOT / "outputs/datasets/생성지표/user_day_baseline_30.csv"
OUT = PROJECT_ROOT / "outputs/dashboard"


def source_signature():
    s = SOURCE.stat()
    links = {p.name: [p.stat().st_size, p.stat().st_mtime_ns] for p in (LOGON_CSV, EMAIL_CSV)}
    return {"name": SOURCE.name, "size": s.st_size, "mtime_ns": s.st_mtime_ns, "version": VERSION, "link_sources": links}


def prepare():
    OUT.mkdir(exist_ok=True)
    df = pd.read_csv(SOURCE, parse_dates=["date"])
    if df.duplicated(["user", "date"]).any():
        raise ValueError("사용자×날짜 중복 행이 있습니다.")
    expected = df.active_day_seq.gt(10) & df.days_since_first.ge(30)
    if not df.is_scored.eq(expected.astype(int)).all():
        raise ValueError("is_scored 조건이 설계안과 다릅니다.")
    # Recompute every baseline from past rows to verify lineage and exclusion of today.
    ordered = df.sort_values(["user", "date"])
    prev = ordered.groupby("user")[list(CORE | LOGON)].shift(1)
    rolling = prev.groupby(ordered.user).rolling(30, min_periods=10)
    means = rolling.mean().reset_index(level=0, drop=True).sort_index()
    stds = rolling.std().reset_index(level=0, drop=True).sort_index()
    max_error = 0.
    for c in CORE | LOGON:
        delta = (df[c + "_mu"] - means[c]).abs().max()
        max_error = max(max_error, float(delta))
        if not np.allclose(df[c + "_mu"], means[c], atol=.000051, equal_nan=True):
            raise ValueError(f"기준선 평균 검증 실패: {c}")
        if not np.allclose(df[c + "_sd"], stds[c], atol=.000051, equal_nan=True):
            raise ValueError(f"기준선 표준편차 검증 실패: {c}")
        z = ((df[c] - means[c]) / stds[c].clip(lower=1)).where(expected)
        if not np.allclose(df[c + "_z"], z, atol=.000051, equal_nan=True):
            raise ValueError(f"z점수 검증 실패: {c}")
    ldap_path = PROJECT_ROOT / "inputs/LDAP/2009-12.csv"
    ldap = pd.read_csv(ldap_path, usecols=["user_id", "employee_name"]).rename(columns={"user_id": "user"})
    df = df.merge(ldap, on="user", how="left", validate="many_to_one")
    for c in ["user", "employee_name", "role", "department", "team", "supervisor", "functional_unit"]:
        df[c] = df[c].fillna("미지정").astype("category")
    # Display-only PC-time link context; merged before scoring so every policy view carries it.
    events = load_link_events()
    events.to_parquet(OUT / "link_events.parquet", index=False)
    df = df.merge(link_context(events, df), on=["user", "date"], how="left", validate="one_to_one")
    thresholds = fit_thresholds(df)
    scored = score(df, thresholds)
    selected = scored[scored.is_scored.eq(1)]
    cols = ["user", "date", "department", *CORE, *[c + "_points" for c in LABELS],
            "overlap_discount", "total_score", "risk_grade", "logon_score", "logon_grade", "logon_alert",
            "review_target", "alert_channel", "period_type", "top_reason", "logon_reason", "link_count", "link_reason"]
    selected[cols].to_csv(OUT / "email_user_day_scores.csv", index=False, encoding="utf-8-sig")
    df.to_parquet(OUT / "baseline.parquet", index=False)
    scored.to_parquet(OUT / "scored.parquet", index=False)
    rates = alert_rates(scored)
    rates.to_csv(OUT / "alert_rates.csv", index=False, encoding="utf-8-sig")
    meta = {"source": source_signature(), "policy": Policy().to_dict(), "thresholds": thresholds,
            "rows": len(df), "scored_rows": len(selected), "warmup_rows": int(df.is_scored.eq(0).sum()),
            "users": int(df.user.nunique()), "start": str(df.date.min().date()), "end": str(df.date.max().date()),
            "calibration_rows": int((expected & df.date.le("2010-05-31")).sum()),
            "baseline_max_rounding_error": max_error, "grade_counts": selected.risk_grade.value_counts().to_dict(),
            "max_score": int(selected.total_score.max()), "normal_period_end": "2010-05-31",
            "labels_used": False, "alert_rates": rates.to_dict("records"),
            "logon_z_cut": LOGON_Z_CUT, "channel_rates": channel_rates(scored).to_dict("records"),
            "link": {"window_min": WINDOW_MIN, "context_days": CONTEXT_DAYS, "events": len(events),
                     "scored_rows_with_link": int(selected.link_count.gt(0).sum())}}
    (OUT / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def ensure_artifacts():
    path = OUT / "metadata.json"
    if path.exists() and all((OUT / f).exists() for f in ["baseline.parquet", "scored.parquet", "email_user_day_scores.csv", "link_events.parquet"]):
        meta = json.loads(path.read_text(encoding="utf-8"))
        if meta.get("source") == source_signature():
            return meta
    return prepare()


if __name__ == "__main__":
    prepare()
