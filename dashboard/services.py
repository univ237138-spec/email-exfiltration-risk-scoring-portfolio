"""Read-only access to frozen v2.2 outputs. No labels or preparation pipeline."""
from pathlib import Path
import hashlib
import io
import json
import zipfile

import numpy as np
import pandas as pd

SOURCE = Path(__file__).resolve().parent / "data"  # not in the repo (CERT r4.2 license)
VERSION = "email-review-v2.2"
POLICY = dict(job_points=2, night_points=1, overlap="max", attention=2,
              caution=3, danger=5, logon_rule="strict")
EMAIL = {
    "corp_ext_send_cnt": "회사계정 외부 발송",
    "new_ext_rcpt_cnt": "신규 외부 수신자",
    "corp_ext_att_mail_cnt": "회사계정 외부 첨부",
    "personal_att_mail_cnt": "개인계정 첨부",
}
LOGON = {"other_pc_logon_cnt": "다른 PC 로그온", "night_logon_cnt": "야간 로그온"}
RULES = {"jobkw_mail": "구직 키워드 메일", "night_mail": "새로운 야간 메일"}
FEATURES = EMAIL | RULES | LOGON
RANK = {"기준선 부족": -1, "정상": 0, "관심": 1, "주의": 2, "위험": 3}
COLORS = {"정상": "#64748B", "관심": "#A57900", "주의": "#C66B17", "위험": "#CC4554", "기준선 부족": "#8794A5"}


def signature(source=SOURCE):
    return tuple((name, (source / name).stat().st_size, (source / name).stat().st_mtime_ns)
                 for name in ("scored.parquet", "metadata.json"))


def validate_data(data, meta):
    if (meta.get("source", {}).get("version") != VERSION or meta.get("policy") != POLICY
            or meta.get("logon_z_cut") != 1.9443):
        raise ValueError("확정된 v2.2 정책과 데이터 버전이 일치하지 않습니다.")
    required = {"user", "date", "employee_name", "department", "role", "is_scored", "base_n",
                "active_day_seq", "days_since_first", "total_score", "risk_grade", "logon_score",
                "logon_grade", "review_target", "logon_alert", "alert_channel", "overlap_discount",
                "jobkw_mail_flag", "night_mail_flag", "night_mail_past30", "jobkw_mail_cnt", "night_mail_cnt"}
    for feature in EMAIL | LOGON:
        required.update([feature, feature + "_mu", feature + "_sd", feature + "_z", feature + "_points"])
    required.update(k + "_points" for k in RULES)
    missing = required - set(data.columns)
    if missing:
        raise ValueError("필수 컬럼 누락: " + ", ".join(sorted(missing)))
    if data[["user", "date"]].isna().any().any() or data.duplicated(["user", "date"]).any():
        raise ValueError("사용자·날짜가 누락되거나 중복되었습니다.")
    if not data.is_scored.isin([0, 1]).all():
        raise ValueError("점수 산출 여부 값이 잘못되었습니다.")
    eligible = data.is_scored.eq(1)
    if not eligible.eq(data.active_day_seq.gt(10) & data.days_since_first.ge(30)).all():
        raise ValueError("기준선 준비 조건과 점수 대상이 일치하지 않습니다.")
    scored = data.loc[eligible]
    for c in EMAIL | LOGON:
        values = scored[[c, c + "_mu", c + "_sd", c + "_z"]].to_numpy(dtype=float)
        thresholds = meta.get("thresholds", {}).get(c, [])
        if len(thresholds) != 3 or not np.isfinite(thresholds).all() or not np.all(np.diff(thresholds) >= 0):
            raise ValueError(f"{c}: 유효하지 않은 점수 경계입니다.")
        expected = sum(scored[c + "_z"].ge(t).astype(int) for t in thresholds)
        if not np.isfinite(values).all() or not scored[c + "_points"].eq(expected).fillna(False).all():
            raise ValueError(f"{c}: 지표값 또는 점수 검산에 실패했습니다.")
    if not scored[["jobkw_mail_flag", "night_mail_flag"]].isin([0, 1]).all().all():
        raise ValueError("규칙형 발생 여부가 잘못되었습니다.")
    if not np.isfinite(scored[["night_mail_past30", "jobkw_mail_cnt", "night_mail_cnt"]].to_numpy(dtype=float)).all():
        raise ValueError("규칙형 지표값이 누락되었습니다.")
    job = scored.jobkw_mail_flag.eq(1).astype(int) * 2
    night = (scored.night_mail_flag.eq(1) & scored.night_mail_past30.eq(0)).astype(int)
    discount = scored[["corp_ext_send_cnt_points", "corp_ext_att_mail_cnt_points"]].min(axis=1)
    email = scored[[c + "_points" for c in EMAIL]].sum(axis=1) + job + night - discount
    logon = scored[[c + "_points" for c in LOGON]].max(axis=1)
    maxz = scored[[c + "_z" for c in LOGON]].max(axis=1)
    la = logon.eq(3) | (logon.eq(2) & maxz.ge(1.9443))
    ea = email.ge(3)
    eg = np.select([email.ge(5), ea, email.ge(2)], ["위험", "주의", "관심"], default="정상")
    lg = np.select([logon.eq(3), la, logon.gt(0)], ["위험", "주의", "관심"], default="정상")
    channels = np.select([ea & la, ea, la], ["둘 다", "이메일", "로그온"], default="")
    expected = dict(total_score=email, logon_score=logon, overlap_discount=discount,
                    jobkw_mail_points=job, night_mail_points=night, review_target=ea | la,
                    logon_alert=la, risk_grade=eg, logon_grade=lg, alert_channel=channels)
    for col, values in expected.items():
        if not scored[col].eq(values).fillna(False).all():
            raise ValueError(f"{col}: 확정 정책과 저장된 결과가 일치하지 않습니다.")
    warmup = data.loc[~eligible]
    point_cols = [c + "_points" for c in FEATURES] + ["total_score", "logon_score"]
    if (not warmup[point_cols].isna().all().all()
            or warmup.review_target.any() or warmup.logon_alert.any()
            or not warmup.risk_grade.eq("기준선 부족").all()
            or not warmup.logon_grade.eq("기준선 부족").all()):
        raise ValueError("기준선 부족 행에 점수 또는 경보가 있습니다.")
    if len(data) != meta["rows"] or int(eligible.sum()) != meta["scored_rows"]:
        raise ValueError("메타데이터와 점수 데이터의 행 수가 다릅니다.")


def load_snapshot(source=SOURCE):
    meta = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    data = pd.read_parquet(source / "scored.parquet")
    data["date"] = pd.to_datetime(data.date)
    validate_data(data, meta)
    data = data.sort_values(["user", "date"]).reset_index(drop=True)
    for c in ["department", "role", "employee_name"]:
        data[c] = data[c].astype("string").fillna("미등록").astype(str)
    data["_priority"] = pd.concat([data.risk_grade.map(RANK), data.logon_grade.map(RANK)], axis=1).max(axis=1)
    data["_id"] = data.user.astype(str) + "|" + data.date.dt.strftime("%Y-%m-%d")
    provenance = {"model": VERSION, "policy": meta["policy"], "thresholds": meta["thresholds"],
                  "logon_z_cut": 1.9443, "source": "dashboard/data/scored.parquet",
                  "sha256": hashlib.sha256((source / "scored.parquet").read_bytes()).hexdigest()}
    return data, meta, provenance


def filter_scope(data, start, end, department="전체", role="전체", query=""):
    mask = data.date.between(pd.Timestamp(start), pd.Timestamp(end))
    if department != "전체":
        mask &= data.department.eq(department)
    if role != "전체":
        mask &= data.role.eq(role)
    if query.strip():
        mask &= (data.user.str.contains(query.strip(), case=False, regex=False)
                 | data.employee_name.str.contains(query.strip(), case=False, regex=False))
    return data.loc[mask]


def summary(scope):
    eligible = scope[scope.is_scored.eq(1)]
    alerts = eligible[eligible.review_target]
    return dict(users=eligible.user.nunique(), review_users=alerts.user.nunique(),
                alerts=len(alerts), danger=int(eligible._priority.eq(3).sum()),
                scored=len(eligible), warmup=int(scope.is_scored.eq(0).sum()))


def reason(row):
    if not row.is_scored:
        return "기준선 준비 중 · 과거 활동일과 관측 기간 확인"
    channels = []
    if row.alert_channel in ("이메일", "둘 다"):
        channels.extend(EMAIL | RULES)
    if row.alert_channel in ("로그온", "둘 다"):
        channels.extend(LOGON)
    if not channels:
        channels = list(FEATURES)
    active = sorted((c for c in channels if row[c + "_points"] > 0),
                    key=lambda c: -row[c + "_points"])
    return " · ".join(f"{FEATURES[c]} +{int(row[c + '_points'])}" for c in active) or "점수 발생 지표 없음"


def review_queue(scope, channel="전체", grade="전체", order="우선순위"):
    all_alerts = scope[scope.review_target]
    queue = all_alerts.copy()
    queue["alert_days"] = queue.user.map(all_alerts.groupby("user").date.nunique())
    if channel != "전체":
        queue = queue[queue.alert_channel.eq(channel)]
    if grade != "전체":
        queue = queue[queue._priority.eq(RANK[grade])]
    sort = {"우선순위": (["_priority", "total_score", "logon_score", "date", "user"], [False, False, False, False, True]),
            "최근 날짜": (["date", "_priority", "user"], [False, False, True]),
            "이메일 점수": (["total_score", "date", "user"], [False, False, True]),
            "로그온 점수": (["logon_score", "date", "user"], [False, False, True]),
            "반복 경보": (["alert_days", "_priority", "date", "user"], [False, False, False, True])}
    cols, ascending = sort[order]
    return queue.sort_values(cols, ascending=ascending)


def queue_table(queue):
    return pd.DataFrame({"사용자 ID": queue.user, "이름": queue.employee_name,
                         "날짜": queue.date.dt.strftime("%Y-%m-%d"),
                         "부서": queue.department, "직무": queue.role,
                         "이메일": queue.total_score.astype(str) + "점 · " + queue.risk_grade,
                         "로그온": queue.logon_score.astype(str) + "점 · " + queue.logon_grade,
                         "경보 채널": queue.alert_channel, "경보일 수": queue.alert_days,
                         "주요 근거": queue.apply(reason, axis=1) if len(queue) else pd.Series(dtype=str)})


def daily_counts(scope, start, end):
    dates = pd.date_range(start, end, freq="D")
    result = pd.DataFrame(index=dates)
    result["관측일 수"] = scope.groupby("date").size().reindex(dates, fill_value=0)
    result["점수 대상"] = scope[scope.is_scored.eq(1)].groupby("date").size().reindex(dates, fill_value=0)
    for key, name in [("이메일", "이메일만"), ("로그온", "로그온만"), ("둘 다", "둘 다")]:
        counts = scope[scope.review_target & scope.alert_channel.eq(key)].groupby("date").size()
        result[name] = counts.reindex(dates, fill_value=0).astype(float).where(result["점수 대상"].gt(0))
    return result


def evidence_table(row, meta):
    rows = []
    for c, label in FEATURES.items():
        eligible = bool(row.is_scored)
        is_rule = c in RULES
        value_col = c + "_cnt" if is_rule else c
        if c == "jobkw_mail":
            explanation = "회사메일 한 통에 키워드 3개 이상 발생 시 2점"
        elif c == "night_mail":
            explanation = f"직전 30활동일 야간 메일 {int(row.night_mail_past30) if pd.notna(row.night_mail_past30) else '—'}일 · 0일이면 1점"
        elif c in ["corp_ext_send_cnt", "corp_ext_att_mail_cnt"]:
            explanation = "외부 발송·외부 첨부 중 큰 점수 한 번 반영"
        elif c in LOGON:
            explanation = "로그온 두 지표 중 큰 점수 한 번 반영"
        else:
            explanation = "개별 점수를 이메일 점수에 반영"
        rows.append({"채널": "로그온" if c in LOGON else "이메일", "지표": label,
                     "현재값": float(row[value_col]),
                     "평소 평균": None if is_rule or not eligible else float(row[c + "_mu"]),
                     "z": None if is_rule or not eligible else float(row[c + "_z"]),
                     "점수": int(row[c + "_points"]) if eligible else None,
                     "적용 근거": explanation if eligible else "기준선 부족 · 점수 미산출",
                     "표준편차": None if is_rule or not eligible else float(row[c + "_sd"]),
                     "z 경계 (1 / 2 / 3점)": "해당 없음" if is_rule else " / ".join(f"{v:.6f}" for v in meta["thresholds"][c])})
    return pd.DataFrame(rows)


def load_links(row, source=SOURCE):
    path = source / "link_events.parquet"
    if not path.exists():
        return None
    data = pd.read_parquet(path)
    required = {"user", "day", "logon_time", "pc", "pc_owner", "mail_time", "mail_user", "n_rcpt"}
    if not required.issubset(data.columns):
        raise ValueError("연결 메일 자료의 필수 컬럼이 없습니다.")
    return data[data.user.eq(row.user) & data.day.between(row.date - pd.Timedelta(days=1), row.date + pd.Timedelta(days=1))].sort_values("logon_time")


def csv_bytes(frame):
    # Keep spreadsheet exports from interpreting externally sourced text as formulas.
    safe = frame.copy()
    for col in safe.select_dtypes(include=["object", "string"]).columns:
        safe[col] = safe[col].map(lambda x: "'" + x if isinstance(x, str) and x.startswith(("=", "+", "-", "@", "\t", "\r")) else x)
    return safe.to_csv(index=False).encode("utf-8-sig")


def investigation_zip(row, history, meta, provenance, filters, links=None):
    context = dict(provenance, user=row.user, date=str(row.date.date()),
                   email_score=None if pd.isna(row.total_score) else int(row.total_score),
                   email_grade=row.risk_grade,
                   logon_score=None if pd.isna(row.logon_score) else int(row.logon_score),
                   logon_grade=row.logon_grade, review_target=bool(row.review_target),
                   reason=reason(row), filters=filters,
                   note="개인 기준선은 당일 제외 직전 30활동일. 점수는 조사 우선순위이며 담당자의 추가 확인이 필요합니다.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as bundle:
        ev = evidence_table(row, meta)
        ev.insert(0, "날짜", str(row.date.date()))
        ev.insert(0, "사용자 ID", row.user)
        bundle.writestr("evidence.csv", csv_bytes(ev))
        cols = ["user", "date", "department", "role", "is_scored", "base_n", "total_score", "risk_grade", "logon_score", "logon_grade", "review_target", "alert_channel"]
        bundle.writestr("history.csv", csv_bytes(history[cols]))
        bundle.writestr("context.json", json.dumps(context, ensure_ascii=False, indent=2, default=str))
        if links is not None and len(links):
            bundle.writestr("linked_mail_candidates.csv", csv_bytes(links))
    return buf.getvalue()


# ---- Dashboard aggregates -------------------------------------------------
UNITS = {"corp_ext_send_cnt": "건", "new_ext_rcpt_cnt": "개 주소", "corp_ext_att_mail_cnt": "건",
         "personal_att_mail_cnt": "건", "jobkw_mail": "건", "night_mail": "건",
         "other_pc_logon_cnt": "회", "night_logon_cnt": "회"}
GRADE_ORDER = ["위험", "주의", "관심", "정상"]


def previous_window(start, end):
    """Same-length window immediately before [start, end]."""
    days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
    prev_end = pd.Timestamp(start) - pd.Timedelta(days=1)
    return prev_end - pd.Timedelta(days=days - 1), prev_end


def user_ranking(scope):
    """One row per user with an alert: the user's strongest alert day plus repeat statistics."""
    alerts = scope[scope.review_target]
    if alerts.empty:
        return alerts.assign(alert_days=pd.Series(dtype=int), first_alert=pd.Series(dtype="datetime64[ns]"),
                             last_alert=pd.Series(dtype="datetime64[ns]"))
    by_user = alerts.groupby("user").date
    best = (alerts.sort_values(["_priority", "total_score", "logon_score", "date"], ascending=False)
            .drop_duplicates("user"))
    best = best.assign(alert_days=best.user.map(by_user.nunique()), first_alert=best.user.map(by_user.min()),
                       last_alert=best.user.map(by_user.max()))
    return best.sort_values(["_priority", "total_score", "logon_score", "alert_days", "date", "user"],
                            ascending=[False, False, False, False, False, True]).reset_index(drop=True)


def user_grade_distribution(scope):
    """Users by their highest channel grade among scored days; warm-up-only users are counted apart."""
    eligible = scope[scope.is_scored.eq(1)]
    top = eligible.groupby("user")._priority.max()
    labels = {3: "위험", 2: "주의", 1: "관심", 0: "정상"}
    counts = {g: int(top.eq(r).sum()) for r, g in labels.items()}
    counts["기준선 부족"] = int(scope.user.nunique() - len(top))
    return counts


def indicator_counts(scope):
    """Scored user-days on which each of the 8 indicators contributed points."""
    eligible = scope[scope.is_scored.eq(1)]
    return {c: int(eligible[c + "_points"].gt(0).sum()) for c in FEATURES}


def score_distribution(scope, column):
    eligible = scope[scope.is_scored.eq(1)]
    return eligible[column].astype(int).value_counts().sort_index()


def _josa(word, with_final, without_final):
    code = ord(word[-1]) - 0xAC00
    return with_final if 0 <= code <= 11171 and code % 28 else without_final


def reason_sentence(row):
    """Plain-language reason built only from indicators that actually scored."""
    if not row.is_scored:
        return "기준선 준비 중이라 점수와 등급을 판정하지 않은 날짜입니다."
    parts = []
    for channel, feats, grade in (("이메일", EMAIL, row.risk_grade), ("로그온", LOGON, row.logon_grade)):
        z_hits = [FEATURES[c] for c in feats if row[c + "_points"] > 0]
        rules = [FEATURES[c] + " 발생" for c in (RULES if channel == "이메일" else {}) if row[c + "_points"] > 0]
        if not z_hits and not rules:
            continue
        text = []
        if z_hits:
            names = "·".join(z_hits)
            text.append(f"{names}{_josa(names, '이', '가')} 개인 기준선을 초과")
        text.extend(rules)
        parts.append(f"{', '.join(text)}하여 {channel} {grade}" if z_hits and not rules
                     else f"{', '.join(text)} → {channel} {grade}")
    if not parts:
        return "점수가 발생한 지표가 없습니다. 이메일·로그온 모두 정상입니다."
    tail = " · 조사 대상" if row.review_target else " · 조사 대상 기준(주의 이상) 미만"
    return " / ".join(parts) + tail
