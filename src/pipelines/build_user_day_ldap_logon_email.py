"""LDAP·logon·email을 합친 사용자×날짜 데이터셋 CSV 생성.

실행: python src/pipelines/build_user_day_ldap_logon_email.py  (data 폴더에서 실행)
출력: outputs/datasets/생성지표/user_day_ldap_logon_email.csv

- 행: logon.csv 활동일 기준 사용자×날짜 전체 (330,452행), 메일이 없는 날은 0
  (회사/개인 계정 = from vs LDAP 주소, 사내 dtaa.com, 경쟁사 6 / 웹메일 15, 수신자 소문자·중복 제거, 야간 = 07시 이전 또는 19시 이후)
- 기존 메일 지표 6개는 src/pipelines/email_user_day/build_email_user_day_dataset.py 함수를 그대로 사용
- 기준선·z·점수는 계산하지 않는다. LDAP 퇴사 정보는 미래 정보라 넣지 않는다
"""
import sys
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src/pipelines/email_user_day"))
from build_email_user_day_dataset import build_daily, load_email, tag_emails  # noqa: E402

OUT = PROJECT_ROOT / "outputs/datasets/생성지표/user_day_ldap_logon_email.csv"
FMT = "%m/%d/%Y %H:%M:%S"

INTERNAL_DOMAIN = "dtaa.com"
COMPETITOR_DOMAINS = {"raytheon.com", "northropgrumman.com", "harris.com", "hp.com", "lockheedmartin.com", "boeing.com"}
WEBMAIL_DOMAINS = {"netzero.com", "gmail.com", "yahoo.com", "verizon.net", "hotmail.com", "bellsouth.net", "aol.com",
                   "optonline.net", "comcast.net", "juno.com", "charter.net", "sbcglobal.net", "earthlink.net",
                   "cox.net", "msn.com"}
LDAP_COLS = ["role", "functional_unit", "department", "team", "supervisor"]


def is_night(t: pd.Series) -> pd.Series:
    return (t.dt.hour < 7) | (t.dt.hour >= 19)


def email_extra(e: pd.DataFrame) -> pd.DataFrame:
    """기존 6개 외 메일 집계: 계정 채널, 수신자 도메인 구분, 첨부, BCC, 야간."""
    t = pd.to_datetime(e["date"], format=FMT)
    rcpts = [{a for a in r.split(";") if a} for r in
             (e["to"].fillna("") + ";" + e["cc"].fillna("") + ";" + e["bcc"].fillna("")).str.lower()]
    doms = [[a.rsplit("@", 1)[-1] for a in r] for r in rcpts]
    corp = e["from"].fillna("").str.lower() == e["ldap_email"].str.lower()
    att = e["attachments"].astype(int)

    x = pd.DataFrame({
        "user": e["user"], "day": e["day"],
        "corp_mail_cnt": corp.astype(int),
        "personal_mail_cnt": (~corp).astype(int),
        "rcpt_cnt": [len(r) for r in rcpts],
        "int_rcpt_cnt": [sum(d == INTERNAL_DOMAIN for d in ds) for ds in doms],
        "competitor_rcpt_cnt": [sum(d in COMPETITOR_DOMAINS for d in ds) for ds in doms],
        "webmail_rcpt_cnt": [sum(d in WEBMAIL_DOMAINS for d in ds) for ds in doms],
        "att_mail_cnt": (att > 0).astype(int),
        "att_cnt": att,
        "bcc_mail_cnt": e["bcc"].notna().astype(int),
        "night_mail_cnt": is_night(t).astype(int),
    })
    return x.groupby(["user", "day"]).sum()


def logon_daily(own_pc: pd.Series) -> pd.DataFrame:
    """로그온 집계. 본인 PC = email.csv에서 쓰는 PC (사용자마다 1대)."""
    lg = pd.read_csv(PROJECT_ROOT / "inputs/events/logon.csv", usecols=["date", "user", "pc", "activity"])
    lg["t"] = pd.to_datetime(lg["date"], format=FMT)
    lg["day"] = lg["t"].dt.normalize()
    lg["minute"] = lg["t"].dt.hour * 60 + lg["t"].dt.minute
    on = lg[lg["activity"] == "Logon"]
    off = lg[lg["activity"] == "Logoff"]
    other = on["pc"] != on["user"].map(own_pc)

    g_on = on.groupby(["user", "day"])
    return pd.concat({
        "logon_cnt": g_on.size(),
        "logoff_cnt": off.groupby(["user", "day"]).size(),
        "logon_pc_cnt": g_on["pc"].nunique(),
        "other_pc_logon_cnt": other.groupby([on["user"], on["day"]]).sum(),
        "night_logon_cnt": is_night(on["t"]).groupby([on["user"], on["day"]]).sum(),
        "first_logon_min": g_on["minute"].min(),
        "last_logoff_min": off.groupby(["user", "day"])["minute"].max(),
    }, axis=1)


def main():
    e = tag_emails(load_email())
    base = build_daily(e)  # logon 격자 330,452행 + 기존 메일 지표 6개 + active_day_seq, days_since_first

    own_pc = pd.read_csv(PROJECT_ROOT / "inputs/events/email.csv", usecols=["user", "pc"]).drop_duplicates().set_index("user")["pc"]
    df = base.join(email_extra(e), how="left").join(logon_daily(own_pc), how="left")

    count_cols = [c for c in df.columns if c.endswith("_cnt")]
    df[count_cols] = df[count_cols].fillna(0).astype(int)
    df["last_logoff_min"] = df["last_logoff_min"].astype("Int64")
    df["first_logon_min"] = df["first_logon_min"].astype("Int64")

    ldap = pd.read_csv(PROJECT_ROOT / "inputs/LDAP/2009-12.csv", usecols=["user_id", *LDAP_COLS]).rename(columns={"user_id": "user"})
    out = df.reset_index().rename(columns={"day": "date"}).merge(ldap, on="user", how="left")
    out["weekday"] = out["date"].dt.dayofweek
    out["is_weekend"] = (out["weekday"] >= 5).astype(int)
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")

    order = (["user", "date", "weekday", "is_weekend", "active_day_seq", "days_since_first"]
             + LDAP_COLS
             + ["logon_cnt", "logoff_cnt", "logon_pc_cnt", "other_pc_logon_cnt", "night_logon_cnt",
                "first_logon_min", "last_logoff_min"]
             + ["email_cnt", "corp_mail_cnt", "personal_mail_cnt",
                "corp_ext_send_cnt", "new_ext_rcpt_cnt", "corp_ext_att_mail_cnt", "personal_att_mail_cnt",
                "jobkw_mail_cnt",
                "rcpt_cnt", "int_rcpt_cnt", "competitor_rcpt_cnt", "webmail_rcpt_cnt",
                "att_mail_cnt", "att_cnt", "bcc_mail_cnt", "night_mail_cnt"])
    out = out[order]
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"rows {len(out):,}  users {out['user'].nunique():,}  cols {len(out.columns)}")
    print("saved", OUT)


if __name__ == "__main__":
    main()
