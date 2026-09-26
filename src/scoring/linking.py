"""PC-time link context for alert reasons (display only; never used in scores).

A link: user V logs on to a PC that is not V's own (own PC = the PC V sends mail from), and within
WINDOW_MIN minutes a mail is sent from that PC by another account. Designed after reading the r4.2
scenario 3 answer files, so it is shown as "확인 필요" context only.
"""
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
LOGON_CSV = PROJECT_ROOT / "inputs/events/logon.csv"
EMAIL_CSV = PROJECT_ROOT / "inputs/events/email.csv"
WINDOW_MIN = 60
CONTEXT_DAYS = 1
FMT = "%m/%d/%Y %H:%M:%S"


def build_link_events(logon, email):
    """One row per (other-PC logon, linked mail). logon: date,user,pc; email: date,user,pc,n_rcpt."""
    email = email.sort_values(["pc", "date"]).reset_index(drop=True)
    owner = email.drop_duplicates("user").set_index("user").pc
    if email.groupby("user").pc.nunique().gt(1).any():
        raise ValueError("사용자마다 메일 PC가 1대라는 가정이 깨졌습니다.")
    pc_owner = pd.Series(owner.index, index=owner.values)
    other = logon[logon.pc.ne(logon.user.map(owner))]
    rows = []
    for pc, g in other.groupby("pc"):
        mails = email[email.pc.eq(pc)]
        if mails.empty:
            continue
        t = mails.date.to_numpy().astype("datetime64[ns]")
        for r in g.itertuples():
            t0 = np.datetime64(r.date.value, "ns")
            lo = np.searchsorted(t, t0, side="right")
            hi = np.searchsorted(t, t0 + np.timedelta64(WINDOW_MIN, "m"), side="right")
            for m in mails.iloc[lo:hi].itertuples():
                if m.user != r.user:
                    rows.append((r.user, r.date, pc, pc_owner.get(pc, "미상"), m.date, m.user, m.n_rcpt))
    cols = ["user", "logon_time", "pc", "pc_owner", "mail_time", "mail_user", "n_rcpt"]
    events = pd.DataFrame(rows, columns=cols)
    events["day"] = events.logon_time.dt.normalize()
    return events


def load_link_events():
    logon = pd.read_csv(LOGON_CSV, usecols=["date", "user", "pc", "activity"])
    logon = logon[logon.activity.eq("Logon")].drop(columns="activity")
    logon["date"] = pd.to_datetime(logon.date, format=FMT)
    email = pd.read_csv(EMAIL_CSV, usecols=["date", "user", "pc", "to", "cc", "bcc"])
    email["date"] = pd.to_datetime(email.date, format=FMT)
    rcpt = email[["to", "cc", "bcc"]].fillna("").agg(";".join, axis=1)
    email["n_rcpt"] = rcpt.map(lambda s: len({a for a in s.lower().split(";") if a}))
    return build_link_events(logon, email[["date", "user", "pc", "n_rcpt"]])


def describe(e):
    return (f"{e.logon_time:%m-%d %H:%M} {e.pc}({e.pc_owner} PC) 로그온 → {e.mail_time:%m-%d %H:%M} "
            f"같은 PC에서 {e.mail_user} 계정 메일 발송 (수신 {e.n_rcpt}명)")


def link_context(events, rows):
    """Per (user, date) in rows: linked mails whose logon day is within ±CONTEXT_DAYS."""
    if events.empty:
        return rows[["user", "date"]].assign(link_count=0, link_reason="")
    shifted = pd.concat([events.assign(date=events.day + pd.Timedelta(k, unit="D"))
                         for k in range(-CONTEXT_DAYS, CONTEXT_DAYS + 1)], ignore_index=True)
    shifted = shifted.sort_values("mail_time")
    agg = shifted.groupby(["user", "date"]).agg(link_count=("mail_time", "size"),
                                                  first=("mail_time", "idxmin")).reset_index()
    agg["link_reason"] = [f"연결 메일 확인 필요: {describe(shifted.loc[i])}" + (f" 외 {n - 1}건" if n > 1 else "")
                          for i, n in zip(agg["first"], agg.link_count)]
    out = rows[["user", "date"]].merge(agg.drop(columns="first"), on=["user", "date"], how="left", validate="one_to_one")
    out["link_count"] = out.link_count.fillna(0).astype(int)
    out["link_reason"] = out.link_reason.fillna("")
    return out
