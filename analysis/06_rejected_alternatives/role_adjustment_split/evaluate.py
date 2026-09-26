"""분할 그룹 하나만 채점한다. 사용법: python evaluate.py 개발용  |  python evaluate.py 평가용 <w>
개발용: 다섯 w를 모두 채점하고 계획 3절 기준으로 w를 고른다.
평가용: 계획 4절대로 고른 w와 w=1(v3)만 채점한다.
"""
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
GROUP = sys.argv[1]
split = pd.read_csv(HERE / "분할.csv", encoding="utf-8-sig")
members = split[split.group == GROUP].set_index("user").scenario
WS = [0, 0.25, 0.5, 0.75, 1] if GROUP == "개발용" else sorted({float(sys.argv[2]), 1.0})
KS = [10, 25, 50, 100]

def score(w):
    w_name = int(w) if float(w).is_integer() else w
    t = pd.read_csv(HERE / f"순위_w{w_name}.csv", encoding="utf-8-sig")
    t = t[t.user.isin(members.index)].reset_index(drop=True)  # 그룹 안에서 다시 순위
    t["scenario"] = t.user.map(members)
    t["insider"] = t.scenario > 0
    out = {"w": w}
    for k in KS:
        h = t.head(k)
        out[f"상위{k}"] = int(h.insider.sum())
        if k == 25:
            out["상위25 시나리오1/2/3"] = "/".join(str(int((h.scenario == s).sum())) for s in [1, 2, 3])
            out["상위25 ITAdmin"] = int((h.role == "ITAdmin").sum())
    f = t[t.priority.isin(["1순위", "2순위"])]
    out["1·2순위 인원"], out["1·2순위 내부자"] = len(f), int(f.insider.sum())
    return out

res = pd.DataFrame([score(w) for w in WS])
pd.set_option("display.width", 200)
print(f"[{GROUP}] 사용자 {len(members)}명, 내부자 {int((members > 0).sum())}명")
print(res.to_string(index=False))
if GROUP == "개발용":
    best = res.sort_values(["상위25", "w"], ascending=[False, False]).iloc[0]
    print(f"\n선택 기준(상위 25명 속 내부자 수, 동점이면 큰 w) → w = {best.w}")
    json.dump({"chosen_w": float(best.w), "dev_results": res.to_dict("records")},
              open(HERE / "개발용_결과.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
else:
    json.dump({"eval_results": res.to_dict("records")}, open(HERE / "평가용_결과.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
