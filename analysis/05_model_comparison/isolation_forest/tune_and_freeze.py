"""Step 1: label-free hyperparameter search inside Feb-May 2010, then freeze models' settings and thresholds."""
import json
import time
from itertools import combinations
import numpy as np
import pandas as pd
from if_common import OUT, CHANNELS, CAL_END, TUNE_TRAIN_END, FROZEN, VERSION, load, features, fit, anomaly, threshold

GRID_SAMPLES = [256, 1024, 4096, 16384]
GRID_TREES = [100, 300, 1000]
SEEDS = [0, 1, 2, 3, 4]


def jaccard(a, b):
    u = len(a | b)
    return len(a & b) / u if u else 1.0


def main():
    d = load()
    cal = d.loc[d.cal]
    tr, ho = cal.loc[cal.date.le(TUNE_TRAIN_END)], cal.loc[cal.date.gt(TUNE_TRAIN_END)]
    target = {'email': float(cal.cur_email.mean()), 'logon': float(cal.cur_logon.mean())}
    rows, chosen = [], {}
    for ch in CHANNELS:
        xtr, xho = features(tr, ch), features(ho, ch)
        for ms in GRID_SAMPLES:
            for nt in GRID_TREES:
                t0 = time.time()
                sets, rates, ties = [], [], []
                for s in SEEDS:
                    m = fit(xtr, nt, ms, s)
                    st, sh = anomaly(m, xtr), anomaly(m, xho)
                    thr = threshold(st, target[ch])
                    sets.append(set(np.flatnonzero(sh >= thr)))
                    rates.append((sh >= thr).mean())
                    ties.append(float(np.isclose(st, thr, rtol=0, atol=1e-12).mean()))
                rows.append(dict(channel=ch, max_samples=ms, n_estimators=nt, cost=ms * nt,
                                 S1_seed_jaccard=float(np.mean([jaccard(a, b) for a, b in combinations(sets, 2)])),
                                 S2_rate_transfer_err=float(np.mean([abs(r / target[ch] - 1) for r in rates])),
                                 S3_boundary_tie=float(np.mean(ties)),
                                 may_alerts_mean=float(np.mean([len(x) for x in sets])),
                                 may_target_alerts=target[ch] * len(ho), seconds=round(time.time() - t0, 1)))
                print(rows[-1], flush=True)
        g = pd.DataFrame([r for r in rows if r['channel'] == ch])
        ok = g[g.S1_seed_jaccard.ge(g.S1_seed_jaccard.max() - .02) & g.S2_rate_transfer_err.le(g.S2_rate_transfer_err.min() + .10)]
        pick = (ok.sort_values(['cost', 'n_estimators']) if len(ok) else g.sort_values('S1_seed_jaccard', ascending=False)).iloc[0]
        chosen[ch] = dict(max_samples=int(pick.max_samples), n_estimators=int(pick.n_estimators),
                          rule_satisfied=bool(len(ok)))
    grid = pd.DataFrame(rows)
    grid.to_csv(OUT / 'hyperparameter_search.csv', index=False, encoding='utf-8-sig')

    frozen = dict(version=VERSION, created='2026-09-22', labels_used=False, clip_negative_z=True,
                  calibration_rows=int(len(cal)), tune_train_rows=int(len(tr)), tune_holdout_rows=int(len(ho)),
                  target_rate=target, features=CHANNELS, chosen=chosen, thresholds={}, raw_z_thresholds={},
                  seed_thresholds={})
    for ch in CHANNELS:
        p = chosen[ch]
        for clip, key in [(True, 'thresholds'), (False, 'raw_z_thresholds')]:
            x = features(cal, ch, clip)
            sc = anomaly(fit(x, p['n_estimators'], p['max_samples'], 0), x)
            thr = threshold(sc, target[ch])
            frozen[key][ch] = dict(threshold=thr, calibration_alert_rate=float((sc >= thr).mean()))
        x = features(cal, ch)
        frozen['seed_thresholds'][ch] = {
            str(s): threshold(anomaly(fit(x, p['n_estimators'], p['max_samples'], s), x), target[ch]) for s in SEEDS}
    FROZEN.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(frozen, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
