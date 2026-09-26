"""Compare pre-specified overlap policies using current v2.1 scores; no production edits."""
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import json
import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / 'overlap_review'
OUT.mkdir(exist_ok=True)
d = pd.read_parquet(PROJECT_ROOT / "outputs/dashboard/scored.parquet")
d = d.loc[d.is_scored.eq(1)].copy()
labels = pd.read_csv(PROJECT_ROOT / "labels/answers/insiders.csv", dtype={'dataset':str})
labels = labels.loc[labels.dataset.eq('4.2')].copy()
for c in ['start','end']:
    labels[c] = pd.to_datetime(labels[c], format='mixed').dt.normalize()
d = d.merge(labels[['user','scenario','start','end']], on='user', how='left', validate='many_to_one')
assert len(labels) == 70 and not d.duplicated(['user','date']).any()
d['incident'] = d.date.ge(d.start) & d.date.le(d.end)
d['normal'] = d.scenario.isna()
a = d.corp_ext_send_cnt_points.astype(int)
b = d.corp_ext_att_mail_cnt_points.astype(int)
lo, hi = np.minimum(a,b), np.maximum(a,b)
original = d.total_score.astype(int)
rest = original-a-b
assert (rest >= 0).all()
variants = {'sum': original, 'max':rest+hi, 'half_overlap':rest+hi+.5*lo,
            'cap_overlap_1':rest+hi+np.minimum(lo,1),
            'drop_send':original-a, 'drop_attachment':original-b}
for k,v in variants.items(): d[k] = v
periods = {'all':pd.Series(True,index=d.index), 'calibration':d.date.le('2010-05-31'),
           'post':d.date.gt('2010-05-31')}
rows=[]
lost=[]
for period, mask in periods.items():
    q=d.loc[mask]
    for name in variants:
        for cut in [3,5]:
            alert=q[name].ge(cut)
            for channel, select in [('email',alert),('review_union',alert|q.logon_alert)]:
                hits=q.loc[select&q.incident]
                normal=q.loc[select&q.normal]
                rows.append(dict(period=period,variant=name,cut=cut,channel=channel,rows=len(q),
                    alerts=int(select.sum()),normal_days=len(normal),normal_users=normal.user.nunique(),
                    hit_days=len(hits),hit_users=hits.user.nunique(),
                    s1=hits.loc[hits.scenario.eq(1),'user'].nunique(),
                    s2=hits.loc[hits.scenario.eq(2),'user'].nunique(),
                    s3=hits.loc[hits.scenario.eq(3),'user'].nunique(),
                    outside_days=int((select&~q.incident&~q.normal).sum())))
            old_users=set(q.loc[q['sum'].ge(cut)&q.incident,'user'])
            new_users=set(q.loc[alert&q.incident,'user'])
            for u in sorted(old_users-new_users):
                lost.append(dict(period=period,variant=name,cut=cut,user=u))
metrics=pd.DataFrame(rows)
metrics.to_csv(OUT/'policy_metrics.csv',index=False,encoding='utf-8-sig')
pd.DataFrame(lost).to_csv(OUT/'lost_detected_users.csv',index=False,encoding='utf-8-sig')
pd.crosstab(a,b).to_csv(OUT/'points_cross_table.csv',encoding='utf-8-sig')

# Equal retrospective review budget: preserve all scores above the tie boundary,
# then uniform selection within the boundary. Expected day counts, no cherry-picked ties.
budget_rows=[]
for period in ['calibration','post']:
    q=d.loc[periods[period]]
    k=int(q['sum'].ge(3).sum())
    for name in variants:
        threshold=q[name].nlargest(k).iloc[-1]
        above=q[name].gt(threshold)
        tied=q[name].eq(threshold)
        fraction=(k-int(above.sum()))/int(tied.sum())
        weights=above.astype(float)+tied.astype(float)*fraction
        assert np.isclose(weights.sum(),k)
        budget_rows.append(dict(period=period,variant=name,budget=k,threshold=float(threshold),
            above=int(above.sum()),ties=int(tied.sum()),tie_fraction=fraction,
            expected_normal_days=float(weights[q.normal].sum()),
            expected_incident_days=float(weights[q.incident].sum()),
            expected_outside_days=float(weights[~q.normal&~q.incident].sum())))
pd.DataFrame(budget_rows).to_csv(OUT/'equal_budget_expected_days.csv',index=False,encoding='utf-8-sig')

# Explain exactly which alerts rely on the second indicator's additional points.
changed=[]
for period,mask in periods.items():
    q=d.loc[mask]
    for cut in [3,5]:
        removed=q.loc[q['sum'].ge(cut)&q['max'].lt(cut)].copy()
        changed.append(dict(period=period,cut=cut,lost_alert_days=len(removed),
            normal_days=int(removed.normal.sum()),incident_days=int(removed.incident.sum()),
            outside_days=int((~removed.normal&~removed.incident).sum()),
            only_pair=int((removed['sum']-removed.corp_ext_send_cnt_points-removed.corp_ext_att_mail_cnt_points).eq(0).sum())))
        if period=='post':
            removed[['user','date','scenario','incident','normal','corp_ext_send_cnt_points',
                     'corp_ext_att_mail_cnt_points','sum','max','logon_alert']].to_csv(
                         OUT/f'post_removed_alerts_ge_{cut}.csv',index=False,encoding='utf-8-sig')
pd.DataFrame(changed).to_csv(OUT/'removed_alert_summary.csv',index=False,encoding='utf-8-sig')
summary={'both_scored_days':int((lo>0).sum()),'all_days':len(d),
         'added_points_due_to_sum':int(lo.sum()),'email_total_points':int(original.sum()),
         'pair_total_points':int((a+b).sum()),
         'source_version':json.loads((PROJECT_ROOT / "outputs/dashboard/metadata.json").read_text())['source']['version']}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary))
print(metrics.loc[(metrics.period=='post')&(metrics.channel=='email')].to_string(index=False))
print('UNION CAUTION')
print(metrics.loc[(metrics.period=='post')&(metrics.channel=='review_union')&(metrics.cut==3)].to_string(index=False))
print('REMOVED',pd.DataFrame(changed).to_string(index=False))
print('BUDGET',pd.DataFrame(budget_rows).to_string(index=False))
print('LOST',pd.DataFrame(lost).to_string(index=False))
