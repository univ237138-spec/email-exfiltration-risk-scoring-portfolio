"""Ablation: email score with vs without int_rcpt_cnt. Labels are loaded after scoring."""
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import json
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
CORE=['corp_ext_send_cnt','new_ext_rcpt_cnt','corp_ext_att_mail_cnt','personal_att_mail_cnt','int_rcpt_cnt']
LOGON=['other_pc_logon_cnt','night_logon_cnt']
KEEP={'E':CORE,'E-int':[c for c in CORE if c!='int_rcpt_cnt']}
FIXED={'관심 이상':2,'주의 이상':3,'위험':5}
TARGETS={'관심 이상':1.39,'주의 이상':0.36,'위험':0.07}


def main():
    d=pd.read_csv(PROJECT_ROOT / "outputs/datasets/생성지표/user_day_baseline_30.csv",parse_dates=['date'])
    d=d[d.is_scored.eq(1)].reset_index(drop=True)
    assert len(d)==308023 and not d.duplicated(['user','date']).any()
    cal=d.date.le('2010-05-31'); post=~cal
    cuts={c:d.loc[cal,c+'_z'].quantile([.99,.9975,.9995]).to_numpy() for c in CORE+LOGON}
    pts={c:pd.Series(np.searchsorted(cuts[c],d[c+'_z'].to_numpy(),side='right'),index=d.index) for c in CORE+LOGON}
    rules=d.jobkw_mail_flag.eq(1).astype(int)*2+(d.night_mail_flag.eq(1)&d.night_mail_past30.eq(0)).astype(int)
    score={v:sum(pts[c] for c in cols)+rules for v,cols in KEEP.items()}
    lscore=np.maximum(pts[LOGON[0]],pts[LOGON[1]])
    existing=pd.read_csv(PROJECT_ROOT / "outputs/dashboard/v1_사내수신자포함_20260921/email_user_day_scores.csv",usecols=['user','date','total_score'],parse_dates=['date'])
    chk=d[['user','date']].assign(s=score['E']).merge(existing,on=['user','date'],validate='one_to_one')
    assert chk.s.eq(chk.total_score).all(),'E must reproduce dashboard total_score'
    assert (score['E-int']<=score['E']).all() and (score['E']-score['E-int']).eq(pts['int_rcpt_cnt']).all()
    # Composite = integer score + max-z tie-breaker in [0,1) (same rule as 이메일_로그온_비교실험 8-2).
    comp={}
    for v,cols in KEEP.items():
        m=d[[c+'_z' for c in cols]].max(axis=1).clip(lower=0)
        comp[v]=score[v]+m/(1+m)
    exact={v:{g:float(comp[v][cal].quantile(1-t/100)) for g,t in TARGETS.items()} for v in KEEP}

    # Label-free: how much of the current alerting depends on int_rcpt_cnt.
    ip=pts['int_rcpt_cnt']
    desc={'int_point_day_percent_post':float(ip[post].gt(0).mean()*100),
          'int_point_days_post':int(ip[post].gt(0).sum())}
    for g,t in FIXED.items():
        a=post&score['E'].ge(t)
        desc[f'{g}_E_alert_days']=int(a.sum())
        desc[f'{g}_with_int_points']=int((a&ip.gt(0)).sum())
        desc[f'{g}_needs_int']=int((a&score['E-int'].lt(t)).sum())
    out=d[['user','date']].copy()
    for v in KEEP:out[v+'_score']=score[v];out[v+'_comp']=comp[v]
    out['int_points']=ip;out['L_score']=lscore
    out.to_parquet(HERE/'비교점수.parquet',index=False)

    # Scores are written before answers are read.
    gt=pd.read_csv(PROJECT_ROOT / "labels/answers/insiders.csv",dtype={'dataset':str})
    gt=gt[gt.dataset.eq('4.2')].copy()
    for c in ['start','end']:gt[c]=pd.to_datetime(gt[c],format='mixed').dt.normalize()
    e=d[['user','date']].merge(gt[['user','scenario','start','end']],on='user',how='left',validate='many_to_one')
    assert len(gt)==70 and e.loc[e.scenario.isna(),'user'].nunique()==930
    inc=e.date.ge(e.start)&e.date.le(e.end); normal=e.scenario.isna(); days=e.loc[post,'date'].nunique()
    rows=[]; det=[]
    def add(method,v,g,mask,th):
        m=mask&post; hit=e[m&inc]
        sc={k:int(hit.loc[hit.scenario.eq(k),'user'].nunique()) for k in [1,2,3]}
        rows.append({'method':method,'variant':v,'grade':g,'threshold':th,'alert_days':int(m.sum()),
            'rate_percent':float(m.sum()/post.sum()*100),'per_day':float(m.sum()/days),
            'fp_users':int(e.loc[m&normal,'user'].nunique()),'fp_days':int((m&normal).sum()),
            'scenario1_hits':sc[1],'scenario2_hits':sc[2],'scenario3_hits':sc[3],
            'all_hits':sum(sc.values()),'email_hits':sc[2]+sc[3]})
        hs=set(hit.user)
        for r in gt.itertuples():det.append({'method':method,'variant':v,'grade':g,'user':r.user,'scenario':r.scenario,'detected':r.user in hs})
    for v in KEEP:
        for g in FIXED:
            add('fixed',v,g,score[v].ge(FIXED[g]),FIXED[g])
            add('exact',v,g,comp[v].ge(exact[v][g]),exact[v][g])
        add('fixed',v+' OR 로그온>=2','주의 이상',score[v].ge(3)|lscore.ge(2),3)
        add('exact',v+' OR 로그온>=2','주의 이상',comp[v].ge(exact[v]['주의 이상'])|lscore.ge(2),exact[v]['주의 이상'])
    res=pd.DataFrame(rows); res.to_csv(HERE/'탐지오탐_비교.csv',index=False,encoding='utf-8-sig')
    dd=pd.DataFrame(det); dd.to_csv(HERE/'정답자별_탐지.csv',index=False,encoding='utf-8-sig')
    changes=[]
    p=dd.pivot_table(index=['user','scenario'],columns=['method','variant','grade'],values='detected',aggfunc='first')
    for method in ['fixed','exact']:
        for g in FIXED:
            a=p[(method,'E-int',g)].astype(bool); b=p[(method,'E',g)].astype(bool)
            changes.append({'method':method,'grade':g,'gained':p[a&~b].index.tolist(),'lost':p[~a&b].index.tolist()})
        a=p[(method,'E-int OR 로그온>=2','주의 이상')].astype(bool); b=p[(method,'E OR 로그온>=2','주의 이상')].astype(bool)
        changes.append({'method':method,'grade':'주의 이상 + 로그온','gained':p[a&~b].index.tolist(),'lost':p[~a&b].index.tolist()})
    (HERE/'summary.json').write_text(json.dumps({'descriptive':desc,'exact_thresholds':exact,'results':rows,'changes':changes},
        ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    pd.set_option('display.width',250)
    print(json.dumps(desc,ensure_ascii=False,indent=1))
    print(res.drop(columns='threshold').round(3).to_string())
    for c in changes:print(c)


if __name__=='__main__':main()
