"""Frozen-policy retrospective evaluation. Does not tune thresholds or alter scoring."""
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import sys
import json
import hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))
from scoring import VERSION, Policy, CORE, LABELS, points

plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 11})
CHANNELS = {'email': '이메일 주의 이상 (≥3점)', 'logon': '로그온 주의 이상',
            'combined': '통합 조사 대상 (이메일 OR 로그온)', 'email_danger': '이메일 위험 (≥5점)'}

def metric(y, p):
    y, p = np.asarray(y, bool), np.asarray(p, bool)
    tp, fn = int((y&p).sum()), int((y&~p).sum())
    fp, tn = int((~y&p).sum()), int((~y&~p).sum())
    def div(a,b): return a/b if b else np.nan
    recall, spec = div(tp,tp+fn), div(tn,tn+fp)
    return dict(TP=tp,FN=fn,FP=fp,TN=tn,N=len(y),precision=div(tp,tp+fp),recall=recall,
                specificity=spec,fpr=div(fp,fp+tn),f1=div(2*tp,2*tp+fp+fn),
                accuracy=div(tp+tn,len(y)),balanced_accuracy=(recall+spec)/2,
                prevalence=div(tp+fn,len(y)),all_negative_accuracy=div(tn+fp,len(y)))

def csv(d, name): d.to_csv(OUT/name,index=False,encoding='utf-8-sig')

def plot(metrics, unit, filename, subtitle, channels=('email','logon','combined')):
    fig, axes = plt.subplots(1,len(channels),figsize=(17,8.2),squeeze=False)
    fig.subplots_adjust(left=.09,right=.97,bottom=.31,top=.76,wspace=.42)
    for ax,ch in zip(axes[0],channels):
        r=metrics.loc[(metrics.period=='post')&(metrics.unit==unit)&(metrics.channel==ch)].iloc[0]
        matrix=np.array([[r.TP,r.FN],[r.FP,r.TN]],dtype=float)
        fractions=matrix/matrix.sum(axis=1,keepdims=True)
        ax.imshow(fractions,cmap='Blues',vmin=0,vmax=1)
        for i in range(2):
            for j in range(2):
                label=[['TP · 탐지','FN · 미탐'],['FP · 오탐','TN · 정상 분류']][i][j]
                ax.text(j,i,f'{label}\n{int(matrix[i,j]):,}\n행 내 {fractions[i,j]:.1%}',ha='center',va='center',
                        fontsize=13,color='white' if fractions[i,j]>.55 else '#142b45',linespacing=1.6)
        ax.set_xticks([0,1],['경보 있음','경보 없음'])
        ax.set_yticks([0,1],['사건기간 안','사건기간 밖\n/ 비내부자'] if unit=='user_day' else ['정답 내부자','비내부자'])
        ax.tick_params(length=0,pad=10)
        ax.set_xlabel('예측',labelpad=9)
        ax.set_title(CHANNELS[ch],fontsize=13,pad=16,weight='bold')
        ax.set_xticks([.5],minor=True); ax.set_yticks([.5],minor=True)
        ax.grid(which='minor',color='white',linewidth=3)
        ax.tick_params(which='minor',length=0)
        for s in ax.spines.values(): s.set_visible(False)
        ax.text(.5,-.24,f"정밀도 {r.precision:.2%}  |  재현율 {r.recall:.2%}\nF1 {r.f1:.3f}  |  오탐률 {r.fpr:.2%}",
                transform=ax.transAxes,ha='center',va='top',fontsize=11,linespacing=1.7)
    fig.text(.045,.945,'현재 점수 정책의 혼동행렬 | '+('사용자·일 단위' if unit=='user_day' else '사용자 단위'),fontsize=22,weight='bold')
    fig.text(.045,.885,subtitle,fontsize=11,color='#526273')
    fig.text(.045,.035,'색 농도 = 실제 클래스별 비율(각 행 합계 100%). 숫자는 '+('사용자·일 수' if unit=='user_day' else '고유 사용자 수')+
             '.\n기존 정답을 활용한 사후 평가이며 독립 검증 성능이 아닙니다.',fontsize=10,color='#526273')
    fig.savefig(OUT/(filename+'.png'),dpi=180)
    fig.savefig(OUT/(filename+'.svg'))
    plt.close(fig)

def main():
    mp=PROJECT_ROOT / "outputs/dashboard/metadata.json"
    meta=json.loads(mp.read_text(encoding='utf-8'))
    assert meta['source']['version']==VERSION
    assert meta['policy']==Policy().to_dict() and meta['policy']['overlap']=='max'
    d=pd.read_parquet(PROJECT_ROOT / "outputs/dashboard/scored.parquet")
    assert len(d)==meta['rows'] and not d.duplicated(['user','date']).any()
    warmup=int(d.is_scored.eq(0).sum())
    d=d.loc[d.is_scored.eq(1)].copy()
    assert len(d)==meta['scored_rows']
    for c in CORE:
        assert points(d[c+'_z'],meta['thresholds'][c]).eq(d[c+'_points']).all()
    pair=d[['corp_ext_send_cnt_points','corp_ext_att_mail_cnt_points']]
    assert pair.min(axis=1).eq(d.overlap_discount).all()
    expected=pair.max(axis=1)+d[[c+'_points' for c in LABELS if c not in ['corp_ext_send_cnt','corp_ext_att_mail_cnt']]].sum(axis=1)
    assert expected.eq(d.total_score).all()
    assert (d.total_score.ge(3)|d.logon_alert).eq(d.review_target).all()
    label_path=PROJECT_ROOT / "labels/answers/insiders.csv"
    labels=pd.read_csv(label_path,dtype={'dataset':str})
    labels=labels.loc[labels.dataset.eq('4.2')].copy()
    assert len(labels)==70 and labels.user.nunique()==70
    for c in ['start','end']: labels[c]=pd.to_datetime(labels[c],format='mixed').dt.normalize()
    d=d.merge(labels[['user','scenario','start','end']],on='user',how='left',validate='many_to_one')
    d['actual_incident']=d.date.ge(d.start)&d.date.le(d.end)
    d['actual_insider']=d.scenario.notna()
    d['email']=d.total_score.ge(3)
    d['email_danger']=d.total_score.ge(5)
    d['logon']=d.logon_alert
    d['combined']=d.review_target
    rows=[]; incidents=[]; decomposition=[]; scopes=[]
    for period,mask in [('post',d.date.gt(meta['normal_period_end'])),('all',pd.Series(True,index=d.index))]:
        q=d.loc[mask].copy()
        users=q.groupby('user',observed=True).agg(actual_insider=('actual_insider','max'),
                 scenario=('scenario','first'),**{c:(c,'max') for c in CHANNELS})
        assert set(labels.user)<=set(users.index)
        assert set(labels.user)<=set(q.loc[q.actual_incident,'user'])
        scopes.append(dict(period=period,rows=len(q),users=len(users),incident_days=int(q.actual_incident.sum()),
                           normal_user_days=int((~q.actual_insider).sum()),
                           insider_outside_days=int((q.actual_insider&~q.actual_incident).sum()),
                           start=str(q.date.min().date()),end=str(q.date.max().date()),observed_dates=q.date.nunique()))
        for ch in CHANNELS:
            rows.append(dict(period=period,unit='user_day',channel=ch,**metric(q.actual_incident,q[ch])))
            rows.append(dict(period=period,unit='user_any_alert',channel=ch,**metric(users.actual_insider,users[ch])))
            hits=set(q.loc[q.actual_incident&q[ch],'user'])
            inside=q.loc[q.actual_incident&q[ch]]
            decomposition.append(dict(period=period,channel=ch,incident_alert_days=len(inside),
                normal_alert_days=int((q[ch]&~q.actual_insider).sum()),
                insider_outside_alert_days=int((q[ch]&q.actual_insider&~q.actual_incident).sum()),
                incident_detected_users=len(hits),insiders_alerted_any_date=int((users.actual_insider&users[ch]).sum()),
                outside_only_insiders=int((users.actual_insider&users[ch]).sum())-len(hits)))
            for _,l in labels.iterrows():
                ud=q.loc[q.user.eq(l.user)]
                incidents.append(dict(period=period,channel=ch,user=l.user,scenario=int(l.scenario),
                    eligible_incident_days=int(ud.actual_incident.sum()),
                    incident_alert_days=int((ud.actual_incident&ud[ch]).sum()),
                    any_period_alert_days=int(ud[ch].sum()),detected_in_incident=l.user in hits))
        if period=='post':
            csv(q[['user','date','scenario','actual_incident','actual_insider',*CHANNELS]],'post_day_predictions.csv')
            csv(users.reset_index(),'post_user_predictions.csv')
    metrics=pd.DataFrame(rows); decomp=pd.DataFrame(decomposition); detail=pd.DataFrame(incidents)
    assert (metrics[['TP','FN','FP','TN']].sum(axis=1)==metrics.N).all()
    assert ((metrics.TP+metrics.FP)==metrics.groupby(['period','unit']).N.transform('first')-(metrics.TN+metrics.FN)).all()
    csv(metrics,'confusion_metrics.csv'); csv(decomp,'alert_decomposition.csv'); csv(detail,'incident_detection_by_user.csv')
    scenario=detail.groupby(['period','channel','scenario']).agg(total_users=('user','size'),detected_users=('detected_in_incident','sum')).reset_index()
    scenario['recall']=scenario.detected_users/scenario.total_users
    csv(scenario,'scenario_incident_recall.csv'); csv(pd.DataFrame(scopes),'scope.csv')
    sc=scopes[0]
    subtitle=f"{VERSION} · 외부 발송/첨부 최댓값 · 위험 ≥5점\n{sc['start']} ~ {sc['end']} · {sc['rows']:,} 사용자·일 · 사건기간 내 {sc['incident_days']:,} 사용자·일"
    plot(metrics,'user_day','01_day_confusion',subtitle)
    plot(metrics,'user_any_alert','02_user_confusion',
         f"{VERSION} · {sc['start']} ~ {sc['end']} · 정답 내부자 70명 / 비내부자 {sc['users']-70}명\n예측 양성 = 해당 기간에 한 번 이상 경보. 사건기간 밖 경보도 포함하므로 사건 탐지율과 다릅니다.")
    plot(metrics,'user_day','03_email_danger_confusion',subtitle,('email','email_danger','combined'))
    manifest=dict(version=VERSION,policy=meta['policy'],warmup_excluded=warmup,scopes=scopes,
        source_score_sha256=hashlib.sha256((PROJECT_ROOT / "outputs/dashboard/scored.parquet").read_bytes()).hexdigest(),
        label_sha256=hashlib.sha256(label_path.read_bytes()).hexdigest(),independent_holdout=False,
        ground_truth='incident start/end date inclusive; daily window proxy, not event-confirmed malicious day',
        checks='unique user-day; policy and source version; individual core points; max aggregation; review union; all 70 incident users covered; matrix sums')
    (OUT/'evaluation_metadata.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(pd.DataFrame(scopes).to_string(index=False))
    print(metrics.loc[metrics.period.eq('post')].to_string(index=False))
    print(decomp.loc[decomp.period.eq('post')].to_string(index=False))
    print(scenario.loc[scenario.period.eq('post')].to_string(index=False))

if __name__=='__main__': main()
