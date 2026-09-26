"""같은 조사량(경보 사용자·일 수)을 무작위로 뽑았을 때의 기대 탐지 성능.

입력: experiments/20260922_혼동행렬_성능평가/post_day_predictions.csv (보정 이후 평가기간)
출력: random_baseline_summary.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import gammaln

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "20260922_혼동행렬_성능평가" / "post_day_predictions.csv"
SEED = 20260924
DRAWS = 2000

d = pd.read_csv(SRC, encoding="utf-8-sig")
n_rows = len(d)
budget = int(d["combined"].sum())

# 정확한 기대값: 내부자별 사건기간 일수 k로 '한 번 이상 뽑힐 확률'(초기하분포)
k = d[d["actual_incident"]].groupby("user").size().to_numpy()


def log_comb(n, r):
    return gammaln(n + 1) - gammaln(r + 1) - gammaln(n - r + 1)


exact = float((1 - np.exp(log_comb(n_rows - k, budget) - log_comb(n_rows, budget))).sum())

rng = np.random.default_rng(SEED)
inc = d["actual_incident"].to_numpy()
ins = d["actual_insider"].to_numpy()
users = d["user"].to_numpy()
rows = []
for _ in range(DRAWS):
    idx = rng.choice(n_rows, budget, replace=False)
    rows.append({
        "detected": len(set(users[idx][inc[idx]])),
        "nonins_fp_users": len(set(users[idx][~ins[idx]])),
        "tp_days": int(inc[idx].sum()),
    })
sim = pd.DataFrame(rows)

model = {
    "detected": int(d[d["combined"] & d["actual_incident"]]["user"].nunique()),
    "nonins_fp_users": int(d[d["combined"] & ~d["actual_insider"]]["user"].nunique()),
    "tp_days": int((d["combined"] & d["actual_incident"]).sum()),
}
out = pd.DataFrame({
    "metric": list(model),
    "model_v2_2": list(model.values()),
    "random_mean": [sim[m].mean() for m in model],
    "random_p2_5": [sim[m].quantile(0.025) for m in model],
    "random_p97_5": [sim[m].quantile(0.975) for m in model],
    "random_max": [sim[m].max() for m in model],
})
out.to_csv(HERE / "random_baseline_summary.csv", index=False, encoding="utf-8-sig")
print(f"rows={n_rows} budget={budget} exact_expected_detected={exact:.2f}")
print(out.to_string(index=False))
print("P(random detected >= model) =", (sim["detected"] >= model["detected"]).mean())
