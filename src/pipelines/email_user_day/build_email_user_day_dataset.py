"""이메일 로그 → 사용자×날짜 행동지표 데이터셋 (기준선이 있는 행만) CSV 생성.

실행: python src/pipelines/email_user_day/build_email_user_day_dataset.py  (data 폴더에서 실행)
출력: outputs/datasets/행동지표/email_user_day_baseline_dataset.csv

정의는 같은 폴더의 설계 문서를 따른다.
- 행: logon 활동일 기준 사용자×날짜 중 과거 활동일 10일 이상인 행
- 기준선: 당일 제외 직전 30개 활동일의 평균(_mu)·표준편차(_sd)
- 보정 z: (x - mu) / max(sd, 1), email_cnt는 기본 z (x - mu) / sd
- 점수: z < 2 → 0 | 2~3 → 1 | 3~4 → 2 | 4 이상 → 3, 구직 키워드 메일 발생 → 2
- 등급: 합계 0~1 정상 | 2 관심 | 3 주의 | 4 이상 위험
- z·점수·등급은 사용자별 첫 30일(달력 기준) 이후 행(is_scored = 1)에만 채운다
"""
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = PROJECT_ROOT / "outputs/datasets/행동지표/email_user_day_baseline_dataset.csv"

INTERNAL_DOMAIN = "@dtaa.com"
JOB_KEYWORDS = {"resume", "salary", "job", "opening", "benefits", "compensation", "part-time",
                "permanent", "career", "interview", "hiring", "position"}
JOB_MIN_WORDS = 3
WINDOW, MIN_HISTORY, WARMUP_DAYS = 30, 10, 30
SIGMA_FLOOR = 1.0

Z_INDICATORS = ["corp_ext_send_cnt", "new_ext_rcpt_cnt", "corp_ext_att_mail_cnt", "personal_att_mail_cnt"]
JOB_POINTS = 2


def load_email() -> pd.DataFrame:
    e = pd.read_csv(PROJECT_ROOT / "inputs/events/email.csv",
                    usecols=["date", "user", "to", "cc", "bcc", "from", "attachments", "content"], dtype=str)
    ldap = pd.read_csv(PROJECT_ROOT / "inputs/LDAP/2009-12.csv", usecols=["user_id", "email"])
    e = e.merge(ldap.rename(columns={"user_id": "user", "email": "ldap_email"}), on="user", how="left")
    e["day"] = pd.to_datetime(e["date"], format="%m/%d/%Y %H:%M:%S").dt.normalize()
    return e


def tag_emails(e: pd.DataFrame) -> pd.DataFrame:
    """메일 한 건마다 채널·외부 수신자·첨부·구직 키워드 태그."""
    low = lambda c: e[c].fillna("").str.lower()
    corp = (low("from") == e["ldap_email"].str.lower()).to_numpy()
    recipients = low("to") + ";" + low("cc") + ";" + low("bcc")
    ext = [{a for a in r.split(";") if a and not a.endswith(INTERNAL_DOMAIN)} for r in recipients]
    has_ext = np.array([len(x) > 0 for x in ext])
    has_att = e["attachments"].astype(int).to_numpy() > 0
    job = np.array([len(JOB_KEYWORDS & set(str(c).lower().split())) >= JOB_MIN_WORDS for c in e["content"]])

    e["ext_rcpts"] = ext
    e["email_cnt"] = 1
    e["corp_ext_send_cnt"] = corp & has_ext
    e["corp_ext_att_mail_cnt"] = corp & has_ext & has_att
    e["personal_att_mail_cnt"] = ~corp & has_att
    e["jobkw_mail_cnt"] = corp & job
    return e


def build_daily(e: pd.DataFrame) -> pd.DataFrame:
    """logon 활동일 격자에 일별 지표를 붙이고, 메일이 없는 날은 0으로 채움."""
    cols = ["email_cnt", "corp_ext_send_cnt", "corp_ext_att_mail_cnt", "personal_att_mail_cnt", "jobkw_mail_cnt"]
    daily = e.groupby(["user", "day"])[cols].sum()

    # 신규 외부 수신자: 사용자별로 주소가 처음 등장한 날짜에만 1회 집계
    first_seen = e[["user", "day", "ext_rcpts"]].explode("ext_rcpts").dropna().groupby(["user", "ext_rcpts"])["day"].min()
    new_rcpt = first_seen.reset_index().groupby(["user", "day"]).size().rename("new_ext_rcpt_cnt")

    logon = pd.read_csv(PROJECT_ROOT / "inputs/events/logon.csv", usecols=["date", "user"])
    logon["day"] = pd.to_datetime(logon["date"], format="%m/%d/%Y %H:%M:%S").dt.normalize()
    grid = logon[["user", "day"]].drop_duplicates().set_index(["user", "day"]).sort_index()

    df = grid.join(daily, how="left").join(new_rcpt, how="left").fillna(0).astype(int)
    df = df[["email_cnt", "corp_ext_send_cnt", "new_ext_rcpt_cnt", "corp_ext_att_mail_cnt",
             "personal_att_mail_cnt", "jobkw_mail_cnt"]]

    days = pd.Series(df.index.get_level_values("day"), index=df.index)
    df["active_day_seq"] = df.groupby(level="user").cumcount() + 1
    df["days_since_first"] = (days - days.groupby(level="user").transform("min")).dt.days
    return df


def add_baseline_and_scores(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["email_cnt", *Z_INDICATORS]:
        grp = df[col].groupby(level="user")
        df[f"{col}_mu"] = grp.transform(lambda s: s.shift(1).rolling(WINDOW, min_periods=MIN_HISTORY).mean())
        df[f"{col}_sd"] = grp.transform(lambda s: s.shift(1).rolling(WINDOW, min_periods=MIN_HISTORY).std())

    df = df[df["active_day_seq"] > MIN_HISTORY].copy()  # 기준선이 있는 행만
    scored = df["days_since_first"] >= WARMUP_DAYS
    df["is_scored"] = scored.astype(int)

    df["email_cnt_z"] = ((df["email_cnt"] - df["email_cnt_mu"]) / df["email_cnt_sd"].replace(0, np.nan)).where(scored)
    for col in Z_INDICATORS:
        z = (df[col] - df[f"{col}_mu"]) / np.maximum(df[f"{col}_sd"], SIGMA_FLOOR)
        df[f"{col}_z"] = z.where(scored)
        pts = pd.Series(np.select([z < 2, z < 3, z < 4], [0, 1, 2], 3), index=df.index)
        df[f"{col}_pts"] = pts.where(scored).astype("Int64")
    df["jobkw_mail_pts"] = pd.Series(np.where(df["jobkw_mail_cnt"] > 0, JOB_POINTS, 0), index=df.index).where(scored).astype("Int64")

    pts_cols = [f"{c}_pts" for c in Z_INDICATORS] + ["jobkw_mail_pts"]
    total = df[pts_cols].sum(axis=1, min_count=1).astype("Int64")
    df["total_pts"] = total
    t = total.fillna(0).to_numpy(dtype=int)
    grade = pd.Series(np.select([t <= 1, t == 2, t == 3], ["정상", "관심", "주의"], "위험"), index=df.index)
    df["risk_grade"] = grade.where(scored)
    return df


def main():
    df = add_baseline_and_scores(build_daily(tag_emails(load_email())))

    order = ["active_day_seq", "days_since_first", "is_scored",
             "email_cnt", "email_cnt_mu", "email_cnt_sd", "email_cnt_z"]
    for col in Z_INDICATORS:
        order += [col, f"{col}_mu", f"{col}_sd", f"{col}_z", f"{col}_pts"]
    order += ["jobkw_mail_cnt", "jobkw_mail_pts", "total_pts", "risk_grade"]

    out = df[order].reset_index().rename(columns={"day": "date"})
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    float_cols = [c for c in out.columns if c.endswith(("_mu", "_sd", "_z"))]
    out[float_cols] = out[float_cols].round(4)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")

    print(f"rows {len(out):,}  users {out['user'].nunique():,}  scored {int(out['is_scored'].sum()):,}")
    print(out.loc[out["is_scored"] == 1, "risk_grade"].value_counts().to_string())
    print("saved", OUT)


if __name__ == "__main__":
    main()
