"""Step 2: apply the frozen IF settings/thresholds, then compare with v2.2 against labels (retrospective)."""
import json
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import numpy as np
import pandas as pd
from if_common import OUT, ROOT, CHANNELS, CAL_END, FROZEN, load, features, fit, anomaly
from scoring import CORE, LOGON

SEEDS = [0, 1, 2, 3, 4]
TIE_SEED, TIE_DRAWS = 20260922, 100


def csv(d, name):
    d.to_csv(OUT / name, index=False, encoding='utf-8-sig')


def ratio(a, b):
    return a / b if b else np.nan


def summary(q, mask):
    mask = np.asarray(mask, bool)
    truth, normal = q.incident.to_numpy(bool), q.normal.to_numpy(bool)
    hit, fp = q.loc[mask & truth], q.loc[mask & normal]
    tp, fn, fpd = int((mask & truth).sum()), int((~mask & truth).sum()), int((mask & ~truth).sum())
    return dict(alert_days=int(mask.sum()), incident_users=hit.user.nunique(), normal_users=fp.user.nunique(),
                incident_recall=hit.user.nunique() / 70, normal_user_fpr=fp.user.nunique() / q.loc[normal, 'user'].nunique(),
                insider_any_alert_users=q.loc[mask & ~normal, 'user'].nunique(),
                incident_alert_days=tp, normal_alert_days=len(fp), insider_outside_alert_days=int((mask & ~truth & ~normal).sum()),
                s1=hit.loc[hit.scenario.eq(1), 'user'].nunique(), s2=hit.loc[hit.scenario.eq(2), 'user'].nunique(),
                s3=hit.loc[hit.scenario.eq(3), 'user'].nunique(),
                TP=tp, FN=fn, FP=fpd, TN=int((~mask & ~truth).sum()),
                day_precision=ratio(tp, tp + fpd), day_recall=ratio(tp, tp + fn), day_f1=ratio(2 * tp, 2 * tp + fpd + fn))


def top_k(scores, k, rng):
    """Top-k mask; rows tied at the k-th score are drawn uniformly at random (label-free)."""
    v = np.sort(scores)[::-1][k - 1]
    above, tied = scores > v, np.flatnonzero(scores == v)
    m = above.copy()
    m[rng.choice(tied, k - above.sum(), replace=False)] = True
    return m, len(tied)


def main():
    fz = json.loads(FROZEN.read_text(encoding='utf-8'))
    d = load()
    cal_mask = d.cal.to_numpy()
    # Refit exactly as frozen (seed 0, full calibration) and score every scored row.
    for tag, clip, key in [('if', True, 'thresholds'), ('raw', False, 'raw_z_thresholds')]:
        for ch in CHANNELS:
            p = fz['chosen'][ch]
            x = features(d, ch, clip)
            m = fit(x[cal_mask], p['n_estimators'], p['max_samples'], 0)
            d[f'{tag}_{ch}_score'] = anomaly(m, x)
            thr = fz[key][ch]['threshold']
            d[f'{tag}_{ch}'] = d[f'{tag}_{ch}_score'].ge(thr)
            assert abs(d.loc[d.cal, f'{tag}_{ch}'].mean() - fz[key][ch]['calibration_alert_rate']) < 1e-12
        d[f'{tag}_review'] = d[f'{tag}_email'] | d[f'{tag}_logon']
    for ch in CHANNELS:  # calibration percentile: share of calibration rows at or above this score
        cs = np.sort(d.loc[d.cal, f'if_{ch}_score'].to_numpy())
        d[f'if_{ch}_top_pct'] = 100 * (len(cs) - np.searchsorted(cs, d[f'if_{ch}_score'].to_numpy(), side='left')) / len(cs)
    for s in SEEDS[1:]:
        for ch in CHANNELS:
            p = fz['chosen'][ch]
            x = features(d, ch)
            d[f'seed{s}_{ch}'] = anomaly(fit(x[cal_mask], p['n_estimators'], p['max_samples'], s), x) >= fz['seed_thresholds'][ch][str(s)]
        d[f'seed{s}_review'] = d[f'seed{s}_email'] | d[f'seed{s}_logon']
    keep = ['user', 'date', 'cal'] + [c for c in d.columns if c.startswith('if_')]
    d[keep].to_parquet(OUT / 'if_scores.parquet', index=False)

    # ---- labels are read only from here on ----
    labels = pd.read_csv(PROJECT_ROOT / "labels/answers/insiders.csv", dtype={'dataset': str})
    labels = labels.loc[labels.dataset.eq('4.2')].copy()
    assert len(labels) == 70 and labels.user.nunique() == 70
    for c in ['start', 'end']:
        labels[c] = pd.to_datetime(labels[c], format='mixed').dt.normalize()
    d = d.merge(labels[['user', 'scenario', 'start', 'end']], on='user', how='left', validate='many_to_one')
    d['incident'] = d.date.ge(d.start) & d.date.le(d.end)
    d['normal'] = d.scenario.isna()
    q = d.loc[d.date.gt(CAL_END)].reset_index(drop=True)
    assert len(q) == 225281 and q.loc[q.normal, 'user'].nunique() == 905

    rows = []
    def add(method, channel, mask, **kw):
        rows.append(dict(method=method, channel=channel, **kw, **summary(q, mask)))
    for ch, col in [('email', 'email'), ('logon', 'logon'), ('review', 'review')]:
        add('현재 v2.2', ch, q[f'cur_{col}'])
        add('IF 고정경계', ch, q[f'if_{col}'])
        add('IF 원z(민감도)', ch, q[f'raw_{col}'])
    for s in SEEDS[1:]:
        add(f'IF 고정경계 seed{s}', 'review', q[f'seed{s}_review'])
    fixed = pd.DataFrame(rows)
    csv(fixed, 'fixed_threshold_metrics.csv')

    # Equal investigation volume per channel (post-hoc ranking, not an operating threshold).
    k = {ch: int(q[f'cur_{ch}'].sum()) for ch in CHANNELS}
    rng = np.random.default_rng(TIE_SEED)
    draws, ties = [], {}
    for i in range(TIE_DRAWS):
        masks = {}
        for ch in CHANNELS:
            masks[ch], ties[ch] = top_k(q[f'if_{ch}_score'].to_numpy(), k[ch], rng)
        r = summary(q, masks['email'] | masks['logon'])
        draws.append(dict(draw=i, **{f'{ch}_{m}': summary(q, masks[ch])[m] for ch in CHANNELS
                                     for m in ['incident_users', 'normal_users']}, **r))
    draws = pd.DataFrame(draws)
    csv(draws, 'equal_volume_draws.csv')
    eq = draws.drop(columns='draw').agg(['mean', 'min', 'max']).T.reset_index(names='metric')
    csv(eq, 'equal_volume_summary.csv')

    # Who changed: incident-period detection per insider.
    ins = q.loc[~q.normal]
    per = ins.groupby('user').agg(scenario=('scenario', 'first'), incident_days=('incident', 'sum'),
        cur_incident_alert_days=('cur_review', lambda s: int((s & ins.loc[s.index, 'incident']).sum())),
        if_incident_alert_days=('if_review', lambda s: int((s & ins.loc[s.index, 'incident']).sum())),
        cur_any_alert_days=('cur_review', 'sum'), if_any_alert_days=('if_review', 'sum')).reset_index()
    per['cur_detected'], per['if_detected'] = per.cur_incident_alert_days.gt(0), per.if_incident_alert_days.gt(0)
    per['change'] = np.select([per.cur_detected & per.if_detected, per.cur_detected, per.if_detected],
                              ['둘 다 탐지', '현재만 탐지', 'IF만 탐지'], default='둘 다 미탐')
    csv(per.sort_values(['change', 'user']), 'incident_detection_by_user.csv')

    # Profile of disagreement days: which indicators reached the v2.2 1-point level.
    meta = json.loads((PROJECT_ROOT / "outputs/dashboard/metadata.json").read_text(encoding='utf-8'))
    level = {c: q[c + '_z'].ge(meta['thresholds'][c][0]) for c in CORE | LOGON}
    level['jobkw_mail'] = q.jobkw_mail_flag.eq(1)
    level['night_mail'] = q.novel_night_mail.eq(1)
    level = pd.DataFrame(level)
    groups = {'둘 다 경보': q.cur_review & q.if_review, '현재만 경보': q.cur_review & ~q.if_review,
              'IF만 경보': ~q.cur_review & q.if_review}
    prof = []
    for g, m in groups.items():
        sub = q.loc[m]
        row = dict(group=g, days=int(m.sum()), incident_days=int(sub.incident.sum()), normal_days=int(sub.normal.sum()),
                   email_alert=int((sub.cur_email if g == '현재만 경보' else sub.if_email).sum()),
                   logon_alert=int((sub.cur_logon if g == '현재만 경보' else sub.if_logon).sum()),
                   no_indicator_at_1pt=int((~level.loc[m].any(axis=1)).sum()),
                   indicators_at_1pt_mean=float(level.loc[m].sum(axis=1).mean()) if m.any() else np.nan)
        row |= {f'share_{c}': float(level.loc[m, c].mean()) if m.any() else np.nan for c in level}
        row |= {f'mean_{c}': float(sub[c].mean()) if m.any() else np.nan for c in CHANNELS['email'] + CHANNELS['logon']}
        prof.append(row)
    csv(pd.DataFrame(prof), 'disagreement_profile.csv')

    # Pre-declared case users.
    a = per.loc[per.change.eq('IF만 탐지')].sort_values(['if_incident_alert_days', 'user'], ascending=[False, True])
    b = per.loc[per.change.eq('현재만 탐지')].sort_values(['cur_incident_alert_days', 'user'], ascending=[False, True])
    c = q.loc[q.normal & q.if_review].groupby('user').size().reset_index(name='n').sort_values(['n', 'user'], ascending=[False, True])
    cases = {'A': a.user.iloc[0] if len(a) else None, 'B': b.user.iloc[0] if len(b) else None,
             'C': c.user.iloc[0] if len(c) else None}

    out = dict(k=k, boundary_ties=ties, cases=cases,
               fixed=fixed.loc[fixed.channel.eq('review')].to_dict('records'),
               equal_volume=eq.loc[eq.metric.isin(['alert_days', 'incident_users', 'normal_users', 'email_incident_users',
                                                   'logon_incident_users', 's1', 's2', 's3'])].to_dict('records'),
               change=per.change.value_counts().to_dict())
    (OUT / 'evaluation_summary.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
