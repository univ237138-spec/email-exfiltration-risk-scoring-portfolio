"""Frozen S=E+L candidate; label-free calibration then retrospective evaluation."""
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import sys
import json
import hashlib
from itertools import combinations
import numpy as np
import pandas as pd
from scipy.stats import hypergeom
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
sys.path.insert(0,str(PROJECT_ROOT / "dashboard"))
from scoring import CORE, LOGON, LABELS, VERSION, Policy, points, LOGON_Z_CUT

def csv(d,name): d.to_csv(OUT/name,index=False,encoding='utf-8-sig')
def ratio(a,b): return a/b if b else np.nan

def summary(q, mask):
    mask=np.asarray(mask,bool)
    truth=q.incident.to_numpy(bool); normal=q.normal.to_numpy(bool)
    hit=q.loc[mask&truth]
    fp=q.loc[mask&normal]
    tp=int((mask&truth).sum()); fn=int((~mask&truth).sum())
    fpd=int((mask&~truth).sum()); tn=int((~mask&~truth).sum())
    return dict(alert_days=int(mask.sum()),incident_alert_days=tp,normal_alert_days=len(fp),
        insider_outside_alert_days=int((mask&~truth&~normal).sum()),
        incident_users=hit.user.nunique(),normal_users=fp.user.nunique(),
        insider_any_alert_users=q.loc[mask&~normal,'user'].nunique(),
        incident_recall=hit.user.nunique()/70,normal_user_fpr=fp.user.nunique()/q.loc[q.normal,'user'].nunique(),
        s1=hit.loc[hit.scenario.eq(1),'user'].nunique(),s2=hit.loc[hit.scenario.eq(2),'user'].nunique(),
        s3=hit.loc[hit.scenario.eq(3),'user'].nunique(),
        TP=tp,FN=fn,FP=fpd,TN=tn,day_precision=ratio(tp,tp+fpd),day_recall=ratio(tp,tp+fn),
        day_f1=ratio(2*tp,2*tp+fpd+fn))

def main():
    path=PROJECT_ROOT / "outputs/dashboard/scored.parquet"
    meta=json.loads((PROJECT_ROOT / "outputs/dashboard/metadata.json").read_text(encoding='utf-8'))
    assert meta['source']['version']==VERSION=='email-review-v2.2'
    assert meta['policy']==Policy().to_dict()
    allrows=pd.read_parquet(path)
    d=allrows.loc[allrows.is_scored.eq(1)].copy()
    assert len(d)==meta['scored_rows'] and not d.duplicated(['user','date']).any()
    for c in CORE|LOGON:
        assert points(d[c+'_z'],meta['thresholds'][c]).eq(d[c+'_points']).all()
    assert (d.jobkw_mail_flag.eq(1)*2).eq(d.jobkw_mail_points).all()
    assert (d.night_mail_flag.eq(1)&d.night_mail_past30.eq(0)).astype(int).eq(d.night_mail_points).all()
    pair=d[['corp_ext_send_cnt_points','corp_ext_att_mail_cnt_points']]
    expected=pair.max(axis=1)+d[[c+'_points' for c in LABELS if c not in ['corp_ext_send_cnt','corp_ext_att_mail_cnt']]].sum(axis=1)
    assert expected.eq(d.total_score).all()
    assert d[[c+'_points' for c in LOGON]].max(axis=1).eq(d.logon_score).all()
    maxz=d[[c+'_z' for c in LOGON]].max(axis=1)
    assert (d.logon_score.eq(3)|(d.logon_score.eq(2)&maxz.ge(LOGON_Z_CUT))).eq(d.logon_alert).all()
    d['E']=d.total_score.astype(int); d['L']=d.logon_score.astype(int); d['S']=d.E+d.L
    d['ref_attention']=d.E.ge(2)|d.L.ge(1)
    d['ref_caution']=d.E.ge(3)|d.logon_alert
    d['ref_danger']=d.E.ge(5)|d.logon_grade.eq('위험')
    assert d.ref_caution.eq(d.review_target).all()
    levels=['attention','caution','danger']
    cal=d.loc[d.date.between('2010-01-01','2010-05-31')]
    targets={lev:int(cal['ref_'+lev].sum()) for lev in levels}
    counts={t:int(cal.S.ge(t).sum()) for t in range(1,17)}
    candidates=[]
    for cuts in combinations(range(1,17),3):
        gaps=[counts[t]-targets[lev] for lev,t in zip(levels,cuts)]
        candidates.append((sum(abs(x) for x in gaps),sum(max(x,0) for x in gaps),*[-t for t in cuts],cuts))
    best=min(candidates)
    thresholds=dict(zip(levels,best[-1]))
    calibration=dict(source_version=VERSION,formula='S = E + L',labels_used=False,
        calibration_rows=len(cal),target_counts=targets,thresholds=thresholds,
        candidate_counts={lev:counts[thresholds[lev]] for lev in levels},
        objective_absolute_error_rows=best[0],tie_break='lower excess, then larger cuts',
        observed_max_S=int(cal.S.max()),theoretical_max_S=15)
    # Freeze before opening the label file.
    (OUT/'frozen_calibration.json').write_text(json.dumps(calibration,indent=2),encoding='utf-8')
    csv(pd.DataFrame([dict(threshold=t,count=n,rate=n/len(cal)) for t,n in counts.items()]),'calibration_all_thresholds.csv')
    csv(cal.groupby(['E','L','S']).size().reset_index(name='rows'),'calibration_score_combinations.csv')
    for lev in levels:d['sum_'+lev]=d.S.ge(thresholds[lev])
    d['ref_grade']=np.select([d.ref_danger,d.ref_caution,d.ref_attention],[3,2,1],default=0)
    d['sum_grade']=np.select([d.sum_danger,d.sum_caution,d.sum_attention],[3,2,1],default=0)
    labels=pd.read_csv(PROJECT_ROOT / "labels/answers/insiders.csv",dtype={'dataset':str})
    labels=labels.loc[labels.dataset.eq('4.2')].copy()
    assert len(labels)==70 and labels.user.nunique()==70
    for col in ['start','end']: labels[col]=pd.to_datetime(labels[col],format='mixed').dt.normalize()
    d=d.merge(labels[['user','scenario','start','end']],on='user',how='left',validate='many_to_one')
    d['incident']=d.date.ge(d.start)&d.date.le(d.end)
    d['normal']=d.scenario.isna()
    q=d.loc[d.date.ge('2010-06-01')].reset_index(drop=True)
    assert set(labels.user)<=set(q.loc[q.incident,'user'])
    metrics=[]; differences=[]
    for period,frame in [('calibration',d.loc[d.date.le('2010-05-31')]),('post',q)]:
        for lev in levels:
            for variant in ['ref','sum']:
                metrics.append(dict(period=period,variant=variant,level=lev,**summary(frame,frame[variant+'_'+lev])))
    metrics=pd.DataFrame(metrics); csv(metrics,'fixed_threshold_metrics.csv')
    for lev in levels:
        old=q['ref_'+lev]; new=q['sum_'+lev]
        oldhit=set(q.loc[old&q.incident,'user']); newhit=set(q.loc[new&q.incident,'user'])
        for status,us in [('lost',oldhit-newhit),('gained',newhit-oldhit)]:
            for u in sorted(us):
                uq=q.loc[q.user.eq(u)&q.incident]
                differences.append(dict(level=lev,change=status,user=u,scenario=int(uq.scenario.iloc[0]),
                    max_S=int(uq.S.max()),old_alert_days=int(uq['ref_'+lev].sum()),new_alert_days=int(uq['sum_'+lev].sum())))
        changed=q.loc[old.ne(new)].copy()
        changed['change']=np.where(changed['sum_'+lev],'new_alert','removed_alert')
        csv(changed[['user','date','scenario','incident','normal','E','L','S','logon_grade','change']],f'changed_rows_{lev}.csv')
        csv(changed.groupby(['change','E','L'],observed=True).agg(rows=('user','size'),incident_rows=('incident','sum'),normal_rows=('normal','sum')).reset_index(),f'changed_combinations_{lev}.csv')
    csv(pd.DataFrame(differences),'incident_user_changes.csv')
    csv(pd.crosstab(q.ref_grade,q.sum_grade).rename_axis('current_grade').reset_index(),'grade_transition.csv')
    csv(q[['user','date','E','L','S','ref_grade','sum_grade','incident','normal',*[v+'_'+lev for v in ['ref','sum'] for lev in levels]]],'post_scores.csv')
    # Equal total review budget. Exact expectations for uniform sampling of boundary ties.
    equal=[]; sims=[]; probabilities=[]
    for lev in levels:
        budget=int(q['ref_'+lev].sum())
        boundary=int(q.S.nlargest(budget).iloc[-1])
        above=q.S.gt(boundary); tied=q.S.eq(boundary)
        N=int(tied.sum()); k=budget-int(above.sum()); frac=k/N
        w=above.astype(float)+tied.astype(float)*frac
        assert np.isclose(w.sum(),budget)
        expected_users={}
        for kind,truth in [('incident',q.incident),('normal',q.normal),('s1',q.incident&q.scenario.eq(1)),
                           ('s2',q.incident&q.scenario.eq(2)),('s3',q.incident&q.scenario.eq(3))]:
            fixed_users=set(q.loc[above&truth,'user'])
            tie_counts=q.loc[tied&truth].groupby('user',observed=True).size()
            expected=float(len(fixed_users))
            for u,m in tie_counts.items():
                prob=1. if u in fixed_users else float(-np.expm1(hypergeom.logpmf(0,N,int(m),k)))
                if u not in fixed_users:expected+=prob
                if kind in ['incident','normal']:
                    probabilities.append(dict(level=lev,kind=kind,user=u,boundary_days=int(m),certain=u in fixed_users,selection_probability=prob))
            expected_users[kind]=expected
        equal.append(dict(level=lev,budget=budget,boundary=boundary,above=int(above.sum()),ties=N,take_from_ties=k,
            tie_fraction=frac,expected_incident_days=float(w[q.incident].sum()),expected_normal_days=float(w[q.normal].sum()),
            expected_outside_days=float(w[~q.normal&~q.incident].sum()),
            expected_incident_users=expected_users['incident'],expected_normal_users=expected_users['normal'],
            expected_s1=expected_users['s1'],expected_s2=expected_users['s2'],expected_s3=expected_users['s3']))
        rng=np.random.default_rng(20260922)
        tied_idx=np.flatnonzero(tied)
        for trial in range(100):
            selected=above.to_numpy().copy()
            selected[rng.choice(tied_idx,size=k,replace=False)]=True
            assert int(selected.sum())==budget
            sims.append(dict(level=lev,trial=trial,**summary(q,selected)))
    csv(pd.DataFrame(equal),'equal_budget_expectation.csv'); csv(pd.DataFrame(sims),'tie_sensitivity_100.csv')
    csv(pd.DataFrame(probabilities),'boundary_user_probabilities.csv')
    outmanifest=dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),version=VERSION,policy=meta['policy'],
        post_rows=len(q),post_users=q.user.nunique(),post_normal_users=q.loc[q.normal,'user'].nunique(),
        post_incident_users=q.loc[q.incident,'user'].nunique(),post_incident_days=int(q.incident.sum()),
        independent_holdout=False,production_changed=False,
        logon_danger_days=int(q.logon_grade.eq('위험').sum()),
        logon_danger_downgraded=int((q.logon_grade.eq('위험')&q.sum_grade.lt(3)).sum()))
    (OUT/'manifest.json').write_text(json.dumps(outmanifest,indent=2),encoding='utf-8')
    plot(metrics,pd.DataFrame(equal))
    print(json.dumps(calibration,indent=2))
    print(metrics.loc[metrics.period.eq('post')].to_string(index=False))
    print('EQUAL BUDGET'); print(pd.DataFrame(equal).to_string(index=False))
    print('USER CHANGES');print(pd.DataFrame(differences).to_string(index=False))
    print('TRANSITIONS');print(pd.crosstab(q.ref_grade,q.sum_grade).to_string())
    print('MANIFEST');print(json.dumps(outmanifest,indent=2))

def plot(metrics,eq):
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':11})
    ref=metrics.query("period=='post' and variant=='ref' and level=='caution'").iloc[0]
    candidate=metrics.query("period=='post' and variant=='sum' and level=='caution'").iloc[0]
    e=eq.loc[eq.level.eq('caution')].iloc[0]
    names=['현재 채널별 판단','합산 + 보정 경계','합산 + 동일 조사량\n(동점 선택 기대값)']
    fig,axes=plt.subplots(1,3,figsize=(15,6.5))
    fig.subplots_adjust(left=.07,right=.97,top=.74,bottom=.26,wspace=.30)
    for ax,title,vals in zip(axes,['사건기간 내 탐지 인원','비내부자 오탐 인원','조사 사용자·일 수'],
            [[ref.incident_users,candidate.incident_users,e.expected_incident_users],
             [ref.normal_users,candidate.normal_users,e.expected_normal_users],
             [ref.alert_days,candidate.alert_days,e.budget]]):
        ax.bar(range(3),vals,color=['#567188','#238a80','#d49b46'],width=.6)
        ax.set_xticks(range(3),names,rotation=17,ha='right');ax.set_title(title,pad=14,weight='bold')
        ax.set_ylim(0,max(vals)*1.23)
        for i,v in enumerate(vals):ax.text(i,v+max(vals)*.035,f'{v:,.1f}' if i==2 and title!='조사 사용자·일 수' else f'{v:,.0f}',ha='center',fontsize=13,weight='bold')
        ax.spines[['top','right']].set_visible(False)
    fig.text(.055,.92,'이메일 + 로그온 합산 실험 | 주의 이상 비교',fontsize=22,weight='bold')
    fig.text(.055,.83,'보정: 2010-01~05 · 평가: 2010-06-01~2011-05-17 · 현재 개별 점수와 중복 처리 유지',fontsize=11,color='#526273')
    fig.text(.055,.025,'동일 조사량은 평가기간 전체 상위 K의 사후 비교입니다. 동점 선택 기대값은 실제 운영 결과가 아닙니다.\n기존 정답을 활용한 탐색적 평가이며 독립 검증 성능이 아닙니다.',fontsize=10,color='#526273')
    for ext in ['png','svg']:fig.savefig(OUT/('통합점수_성능비교.'+ext),dpi=180)
    plt.close(fig)

if __name__=='__main__':main()
