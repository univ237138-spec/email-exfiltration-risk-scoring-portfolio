"""이메일·LDAP·로그온 CSV를 합친 사용자×날짜 데이터셋 (기준선 필터 전 전체 행) CSV 생성.

실행: python src/pipelines/build_email_user_day_merged.py  (data 폴더에서 실행)
출력: outputs/datasets/생성지표/email_user_day_merged.csv

archive/행동지표_misc/build_email_user_day_dataset.py의 build_daily() 결과(74행 join 직후 상태)를 그대로 저장한다.
- 행: logon.csv 활동일 기준 사용자×날짜 전체, 메일이 없는 날은 0
- 기준선·z·점수는 계산하지 않는다
"""
import sys
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
sys.path.insert(0, str(PROJECT_ROOT / "src/pipelines/email_user_day"))
from build_email_user_day_dataset import build_daily, load_email, tag_emails  # noqa: E402

OUT = PROJECT_ROOT / "outputs/datasets/생성지표/email_user_day_merged.csv"


def main():
    df = build_daily(tag_emails(load_email()))
    out = df.reset_index().rename(columns={"day": "date"})
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out = out[["user", "date", "active_day_seq", "days_since_first", "email_cnt", "corp_ext_send_cnt",
               "new_ext_rcpt_cnt", "corp_ext_att_mail_cnt", "personal_att_mail_cnt", "jobkw_mail_cnt"]]
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"rows {len(out):,}  users {out['user'].nunique():,}")
    print("saved", OUT)


if __name__ == "__main__":
    main()
