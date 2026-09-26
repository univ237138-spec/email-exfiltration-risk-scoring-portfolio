"""사용자×날짜 데이터셋에 직전 30개 활동일 베이스라인·z점수를 붙인 CSV 생성.

실행: python src/pipelines/build_user_day_baseline_30.py  (data 폴더에서 실행)
입력: outputs/datasets/생성지표/user_day_ldap_logon_email.csv
출력: outputs/datasets/생성지표/user_day_baseline_30.csv

설계: docs/methods/베이스라인_설계안.md (8절 추천안 적용)
- 기준선: 사용자별, 당일 제외 직전 30개 활동일, 최소 10일 → _mu, _sd
- z = (x - mu) / max(sd, 1)  (모든 z 지표 공통, email_cnt 포함)
- 규칙형: 오늘 발생 여부(_flag) + 직전 30개 활동일 중 발생한 날 수(_past30)
- 점수 대상(is_scored): active_day_seq > 10 이고 days_since_first >= 30. 대상이 아닌 행은 z·flag를 비움
- 주말 행도 평일과 같이 기준선에 포함
"""
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SRC = PROJECT_ROOT / "outputs/datasets/생성지표/user_day_ldap_logon_email.csv"
OUT = PROJECT_ROOT / "outputs/datasets/생성지표/user_day_baseline_30.csv"

WINDOW, MIN_HISTORY, WARMUP_DAYS = 30, 10, 30
SIGMA_FLOOR = 1.0

CORE = ["corp_ext_send_cnt", "new_ext_rcpt_cnt", "corp_ext_att_mail_cnt", "personal_att_mail_cnt", "int_rcpt_cnt"]
REFERENCE = ["email_cnt", "corp_mail_cnt", "personal_mail_cnt", "rcpt_cnt", "bcc_mail_cnt"]
LOGON_EXT = ["other_pc_logon_cnt", "night_logon_cnt"]
Z_COLS = CORE + REFERENCE + LOGON_EXT
RULE = {"jobkw_mail_cnt": "jobkw_mail", "night_mail_cnt": "night_mail"}


def past_window(df: pd.DataFrame, cols: list[str], how: str) -> pd.DataFrame:
    """사용자별로 당일을 제외한 직전 WINDOW개 행의 통계 (최소 MIN_HISTORY개)."""
    prev = df.groupby("user")[cols].shift(1)
    roll = prev.groupby(df["user"]).rolling(WINDOW, min_periods=MIN_HISTORY)
    return getattr(roll, how)().reset_index(level=0, drop=True).sort_index()


def main():
    df = pd.read_csv(SRC).sort_values(["user", "date"]).reset_index(drop=True)

    seq_ok = df.groupby("user")["active_day_seq"].apply(lambda s: (s.to_numpy() == np.arange(1, len(s) + 1)).all())
    assert seq_ok.all(), "active_day_seq가 1부터 연속되지 않는 사용자가 있습니다"

    scored = (df["active_day_seq"] > MIN_HISTORY) & (df["days_since_first"] >= WARMUP_DAYS)
    df["is_scored"] = scored.astype(int)
    df["base_n"] = (df["active_day_seq"] - 1).clip(upper=WINDOW).where(df["active_day_seq"] > MIN_HISTORY).astype("Int64")

    mu = past_window(df, Z_COLS, "mean")
    sd = past_window(df, Z_COLS, "std")
    new_cols = {}
    for c in Z_COLS:
        new_cols[f"{c}_mu"] = mu[c]
        new_cols[f"{c}_sd"] = sd[c]
        new_cols[f"{c}_z"] = ((df[c] - mu[c]) / np.maximum(sd[c], SIGMA_FLOOR)).where(scored)

    occurred = df[list(RULE)].gt(0).astype(int)
    past = past_window(occurred.assign(user=df["user"]), list(RULE), "sum")
    for c, name in RULE.items():
        new_cols[f"{name}_flag"] = occurred[c].where(scored).astype("Int64")
        new_cols[f"{name}_past30"] = past[c].astype("Int64")

    out = pd.concat([df, pd.DataFrame(new_cols)], axis=1)
    float_cols = [c for c in out.columns if c.endswith(("_mu", "_sd", "_z"))]
    out[float_cols] = out[float_cols].round(4)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")

    print(f"rows {len(out):,}  cols {len(out.columns)}  scored {int(out['is_scored'].sum()):,}")
    print("saved", OUT)


if __name__ == "__main__":
    main()
