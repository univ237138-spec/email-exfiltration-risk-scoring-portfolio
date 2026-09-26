"""개발용/평가용 분할 파일 생성. 시드 20260922, 내부자는 시나리오별 절반, 비내부자는 절반.
실행: 작업공간 루트에서 python experiments/20260922_직무보정_분할검증/make_split.py
"""
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 20260922

users = pd.read_csv(PROJECT_ROOT / "inputs/LDAP/2009-12.csv", usecols=["user_id"]).user_id.sort_values().tolist()
ins = pd.read_csv(PROJECT_ROOT / "labels/answers/insiders.csv")
ins = ins[ins.dataset.astype(str) == "4.2"].set_index("user").scenario
rng = np.random.default_rng(SEED)
rows = []
for sc in sorted(ins.unique()):
    us = sorted(ins[ins == sc].index)
    rng.shuffle(us)
    half = len(us) // 2
    rows += [(u, "개발용" if i < half else "평가용", int(sc)) for i, u in enumerate(us)]
normal = sorted(set(users) - set(ins.index))
rng.shuffle(normal)
half = len(normal) // 2
rows += [(u, "개발용" if i < half else "평가용", 0) for i, u in enumerate(normal)]
s = pd.DataFrame(rows, columns=["user", "group", "scenario"]).sort_values("user")
s.to_csv(HERE / "분할.csv", index=False, encoding="utf-8-sig")
print(pd.crosstab(s.scenario, s.group, margins=True))
