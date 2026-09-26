"""Retrospective incident-window association; no changes to production models.

Dependencies: numpy, pandas, scipy, sklearn, matplotlib, pyarrow.
Logistic MLE + user-cluster CR1 covariance implemented with NumPy/SciPy;
verified against sklearn unpenalized Newton-Cholesky logistic regression.
"""
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import json, hashlib, sys, warnings
import numpy as np
import pandas as pd
import scipy
from scipy.special import expit
from scipy.stats import t, norm, f
from sklearn.linear_model import LogisticRegression
import sklearn
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
Z = ['corp_ext_send_cnt_z','new_ext_rcpt_cnt_z','corp_ext_att_mail_cnt_z',
     'personal_att_mail_cnt_z','other_pc_logon_cnt_z','night_logon_cnt_z']
FEATURES = Z + ['jobkw_mail_flag','new_night_mail_flag']
LABELS = dict(zip(FEATURES, ['회사계정 외부 발송','신규 외부 수신자','회사계정 외부 첨부',
    '개인계정 첨부','다른 PC 로그온','야간 로그온','구직 키워드 메일','새로운 야간 메일']))

def save(d, name, index=False):
    d.to_csv(OUT/name, index=index, encoding='utf-8-sig')

def bh(p):
    p=np.asarray(p); ix=np.argsort(p); q=np.empty(len(p))
    q[ix]=np.minimum(1,np.minimum.accumulate((p[ix]*len(p)/np.arange(1,len(p)+1))[::-1])[::-1])
    return q

def fit(data, cols, name, verify=False):
    X=np.column_stack([np.ones(len(data)),data[cols].to_numpy(float)])
    y=data.y.to_numpy(float)
    groups, users=pd.factorize(data.user,sort=True)
    n,k=X.shape; g=len(users)
    assert np.isfinite(X).all() and 0<y.sum()<n and np.linalg.matrix_rank(X)==k
    # Scale for stable numerical optimization, then map coefficients/covariance back.
    scale=np.r_[1,np.std(X[:,1:],axis=0)]
    A=X/scale
    b=np.zeros(k); b[0]=np.log(y.mean()/(1-y.mean()))
    def nll(bb):
        eta=A@bb
        return np.sum(np.logaddexp(0,eta)-y*eta)
    converged=False
    for iteration in range(100):
        p=expit(A@b); score=A.T@(y-p)
        H=A.T@((p*(1-p))[:,None]*A)
        step=np.linalg.solve(H,score)
        old=nll(b); rate=1.
        while nll(b+rate*step)>old+1e-9 and rate>1e-8: rate*=.5
        b+=rate*step
        if np.max(np.abs(rate*step))<1e-8:
            converged=True; break
    p=expit(A@b); score=A.T@(y-p)
    H=A.T@((p*(1-p))[:,None]*A)
    bread=np.linalg.inv(H)
    scores=A*(y-p)[:,None]
    U=np.zeros((g,k)); np.add.at(U,groups,scores)
    correction=g/(g-1)*(n-1)/(n-k)
    cov_s=correction*bread@(U.T@U)@bread
    beta=b/scale; cov=cov_s/np.outer(scale,scale)
    se=np.sqrt(np.diag(cov)); naive=np.sqrt(np.diag(bread))/scale
    critical=t.ppf(.975,g-1)
    tab=pd.DataFrame({'term':['const']+cols,'beta':beta,'cluster_se':se,'naive_se':naive,
        'OR':np.exp(beta),'CI_low':np.exp(beta-critical*se),'CI_high':np.exp(beta+critical*se),
        'p_cluster':2*t.sf(np.abs(beta/se),g-1),'p_naive':2*norm.sf(np.abs(beta/naive))})
    tab['q_BH']=np.nan
    selected=tab.term.isin(FEATURES)
    tab.loc[selected,'q_BH']=bh(tab.loc[selected,'p_cluster'])
    tab['label']=tab.term.map(LABELS).fillna(tab.term)
    tab['model']=name
    ll=-nll(b); py=y.mean(); ll0=float(np.sum(y*np.log(py)+(1-y)*np.log1p(-py)))
    diag=dict(model=name,n=n,users=g,positive_days=int(y.sum()),positive_users=int(data.loc[data.y.eq(1),'user'].nunique()),
        parameters=k,converged=converged,iterations=iteration+1,max_abs_scaled_score=float(np.max(np.abs(score))),
        information_condition=float(np.linalg.cond(H)),ll=ll,ll_null=ll0,mcfadden=1-ll/ll0,
        min_probability=float(p.min()),max_probability=float(p.max()),cr1_correction=correction,df=g-1)
    assert converged and np.max(np.abs(score))<1e-4, diag
    assert np.linalg.eigvalsh(cov).min()>-1e-10
    if verify:
        ref=LogisticRegression(C=np.inf,solver='newton-cholesky',tol=1e-11,max_iter=100)
        ref.fit(A[:,1:],y)
        bb=np.r_[ref.intercept_,ref.coef_.ravel()]
        diag['sklearn_max_abs_beta_difference']=float(np.max(np.abs(bb/scale-beta)))
        assert np.allclose(bb/scale,beta,atol=2e-6,rtol=2e-6)
        U2=pd.DataFrame(scores).groupby(groups).sum().to_numpy()
        assert np.allclose(U,U2,atol=1e-9)
        pd.DataFrame(cov,index=['const']+cols,columns=['const']+cols).to_csv(OUT/'main_covariance.csv',encoding='utf-8-sig')
    save(tab,name+'_or.csv')
    print(name, json.dumps(diag),flush=True)
    return tab,diag,beta,cov

def main():
    sp=PROJECT_ROOT / "outputs/dashboard/scored.parquet"
    lp=PROJECT_ROOT / "labels/answers/insiders.csv"
    d=pd.read_parquet(sp)
    assert not d.duplicated(['user','date']).any()
    n_original=len(d); n_warmup=int(d.is_scored.eq(0).sum())
    d=d.loc[d.is_scored.eq(1)&d.date.ge('2010-06-01')].copy()
    labels=pd.read_csv(lp,dtype={'dataset':str})
    labels=labels.loc[labels.dataset.eq('4.2')]
    assert len(labels)==70 and labels.user.nunique()==70
    for col in ['start','end']: labels[col]=pd.to_datetime(labels[col],format='mixed').dt.normalize()
    d=d.merge(labels[['user','scenario','start','end']],on='user',how='left',validate='many_to_one')
    d['y']=(d.date.ge(d.start)&d.date.le(d.end)).astype(int)
    d['new_night_mail_flag']=(d.night_mail_flag.eq(1)&d.night_mail_past30.eq(0)).astype(int)
    assert np.isfinite(d[FEATURES].to_numpy(float)).all()
    assert (len(d),d.user.nunique(),int(d.y.sum()))==(225281,975,1364)
    prior=pd.read_csv(ROOT/'20260922_혼동행렬_성능평가/post_day_predictions.csv',parse_dates=['date'])
    checked=d[['user','date','y']].merge(prior[['user','date','actual_incident']],on=['user','date'],validate='one_to_one')
    assert len(checked)==len(d) and (checked.y.astype(bool)==checked.actual_incident).all()
    save(d[['user','date','scenario','y',*FEATURES]],'analysis_rows.csv')
    corr=d[FEATURES].corr(); spearman=d[FEATURES].corr(method='spearman')
    save(corr,'correlation_pearson.csv',True); save(spearman,'correlation_spearman.csv',True)
    inv=np.linalg.inv(corr.to_numpy()); vif=pd.DataFrame({'term':FEATURES,'label':[LABELS[c] for c in FEATURES],'VIF':np.diag(inv)})
    for j,col in enumerate(FEATURES):
        target=d[col].to_numpy(float); others=np.column_stack([np.ones(len(d)),d[[c for c in FEATURES if c!=col]].to_numpy(float)])
        coef=np.linalg.lstsq(others,target,rcond=None)[0]
        direct=np.sum((target-target.mean())**2)/np.sum((target-others@coef)**2)
        assert np.isclose(direct,vif.iloc[j].VIF,rtol=1e-8)
    save(vif,'vif.csv')
    summaries=[]; support=[]
    for col in FEATURES:
        for yy in [0,1]:
            q=d.loc[d.y.eq(yy),col]
            summaries.append(dict(term=col,label=LABELS[col],y=yy,n=len(q),mean=q.mean(),median=q.median(),p95=q.quantile(.95),max=q.max(),positive_days=int(q.gt(0).sum())))
        for scenario in [0,1,2,3]:
            mask=d.y.eq(0) if scenario==0 else d.y.eq(1)&d.scenario.eq(scenario)
            q=d.loc[mask]; active=q.loc[q[col].gt(0)]
            support.append(dict(term=col,scenario='y0' if scenario==0 else str(scenario),days=len(q),active_days=len(active),users=q.user.nunique(),active_users=active.user.nunique()))
    save(pd.DataFrame(summaries),'feature_summary_by_y.csv'); save(pd.DataFrame(support),'feature_support_by_scenario.csv')
    tables=[]; diagnostics=[]
    base,diag,beta,cov=fit(d,FEATURES,'main',True); tables.append(base); diagnostics.append(diag)
    clipped=d.copy(); clipped[Z]=clipped[Z].clip(lower=0)
    tab,di,_,_=fit(clipped,FEATURES,'positive_z'); tables.append(tab); diagnostics.append(di)
    tab,di,_,_=fit(d,[c for c in FEATURES if c!='jobkw_mail_flag'],'without_jobkw'); tables.append(tab); diagnostics.append(di)
    # Exclude every observation of scenario-2 accounts, not just positive dates.
    no2=d.loc[~d.scenario.eq(2)].copy()
    # Omit a predictor with zero support among either outcome class; record explicitly.
    no2cols=[c for c in FEATURES if no2[c].nunique()>1 and all(no2.loc[no2.y.eq(yy),c].gt(0).any() for yy in [0,1])]
    tab,di,_,_=fit(no2,no2cols,'exclude_scenario2'); di['omitted_no_positive_support']=[c for c in FEATURES if c not in no2cols]; tables.append(tab); diagnostics.append(di)
    month_support=d.groupby(d.date.dt.to_period('M')).y.agg(['size','sum'])
    save(month_support,'monthly_label_support.csv',True)
    # May 2011 has no positive outcome; its fixed effect diverges to -infinity.
    # Keep all months in MAIN. Limit only this sensitivity to months with both outcomes.
    supported_months=month_support.index[(month_support['sum']>0)&(month_support['sum']<month_support['size'])]
    restricted=d.loc[d.date.dt.to_period('M').isin(supported_months)].copy()
    tab,di,_,_=fit(restricted,FEATURES,'month_supported_unadjusted'); tables.append(tab); diagnostics.append(di)
    months=pd.get_dummies(restricted.date.dt.to_period('M').astype(str),prefix='month',drop_first=True,dtype=float)
    monthly=pd.concat([restricted,months],axis=1)
    tab,di,_,_=fit(monthly,FEATURES+list(months),'month_adjusted'); tables.append(tab); diagnostics.append(di)
    # Hinge model checks common slope for decreases and increases; not a full nonlinear model.
    hinge=d.copy()
    for c in Z: hinge[c+'_positive']=hinge[c].clip(lower=0)
    hcols=[c+'_positive' for c in Z]
    tab,di,hbeta,hcov=fit(hinge,FEATURES+hcols,'hinge_at_zero')
    indices=[1+(FEATURES+hcols).index(c) for c in hcols]
    effect=hbeta[indices]; vc=hcov[np.ix_(indices,indices)]
    wf=float(effect@np.linalg.solve(vc,effect)/len(indices))
    di['hinge_joint_F']=wf; di['hinge_joint_p']=float(f.sf(wf,len(indices),di['df']))
    positive=[]
    for c in Z:
        a=1+(FEATURES+hcols).index(c); b=1+(FEATURES+hcols).index(c+'_positive')
        val=hbeta[a]+hbeta[b]; se=np.sqrt(hcov[a,a]+hcov[b,b]+2*hcov[a,b]); crit=t.ppf(.975,di['df'])
        positive.append(dict(term=c,label=LABELS[c],OR=np.exp(val),CI_low=np.exp(val-crit*se),CI_high=np.exp(val+crit*se),p_cluster=2*t.sf(abs(val/se),di['df'])))
    save(pd.DataFrame(positive),'hinge_positive_slopes.csv')
    tables.append(tab); diagnostics.append(di)
    save(pd.concat(tables,ignore_index=True),'all_models_or.csv')
    save(pd.DataFrame(diagnostics),'model_diagnostics.csv')
    manifest=dict(source_rows=n_original,warmup_excluded_all_period=n_warmup,period_start=str(d.date.min().date()),period_end=str(d.date.max().date()),
        rows=len(d),users=d.user.nunique(),positive_days=int(d.y.sum()),positive_users=d.loc[d.y.eq(1),'user'].nunique(),
        independent_holdout=False,scope='retrospective explanatory association, not prospective detection',
        label='CERT r4.2 incident start/end inclusive user-day proxy',
        input_sha256={str(p.relative_to(ROOT.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [sp,lp]},
        versions=dict(python=sys.version,numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__,sklearn=sklearn.__version__),
        implementation='NumPy/SciPy Newton MLE + CR1 sandwich; t(df=users-1); sklearn independent coefficient verification; statsmodels unavailable',
        diagnostics=diagnostics,checks=['unique user-day','finite design','exact match to existing labels','225281 rows / 975 users / 1364 positive days',
        'full rank and converged score','VIF independently checked with auxiliary OLS','main coefficients checked with sklearn','cluster scores checked with pandas groupby'])
    (OUT/'analysis_metadata.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    plots(base,corr,vif)
    print(base[['label','OR','CI_low','CI_high','p_cluster','q_BH']].to_string(index=False),flush=True)

def plots(base,corr,vif):
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':11})
    q=base.loc[base.term.isin(FEATURES)].set_index('term').loc[FEATURES].reset_index()
    fig,ax=plt.subplots(figsize=(12.5,6.8)); fig.subplots_adjust(left=.22,right=.65,top=.84,bottom=.17)
    pos=np.arange(len(q))
    ax.errorbar(q.OR,pos,xerr=[q.OR-q.CI_low,q.CI_high-q.OR],fmt='o',color='#176b91',capsize=4)
    ax.axvline(1,color='#9b4b36',linestyle='--',lw=1)
    ax.set_yticks(pos,q.label); ax.invert_yaxis(); ax.set_xscale('log'); ax.grid(axis='x',alpha=.2)
    ax.set_xlabel('조정 OR (로그 축) · 사용자 군집 보정 95% 신뢰구간')
    for i,row in q.iterrows():
        ax.text(1.04,i,f'{row.OR:.2f}  [{row.CI_low:.2f}, {row.CI_high:.2f}]',transform=ax.get_yaxis_transform(),va='center',fontsize=11)
    fig.text(.06,.94,'행동지표와 사건기간의 관련성',fontsize=21,weight='bold')
    fig.text(.06,.88,'225,281 사용자·일 / 975명 · 8개 지표 동시 투입 · 부호 있는 z 기준',fontsize=11)
    fig.text(.06,.045,'건수형: 보정 z 1단위 증가 / 이진형: 0→1. 인과효과·유출 확률·개별 경보 기여도가 아닙니다.\n선형 logit 주 모형의 결과이며, 기울기 형태와 시나리오에 대한 민감도는 보고서를 함께 확인하세요.',fontsize=10,color='#536271')
    fig.savefig(OUT/'01_OR_신뢰구간.png',dpi=170); fig.savefig(OUT/'01_OR_신뢰구간.svg'); plt.close(fig)
    fig,ax=plt.subplots(figsize=(10.5,9)); fig.subplots_adjust(left=.23,bottom=.25,top=.9,right=.87)
    im=ax.imshow(corr,vmin=-1,vmax=1,cmap='RdBu_r')
    names=[LABELS[c] for c in FEATURES]
    ax.set_xticks(range(8),names,rotation=45,ha='right'); ax.set_yticks(range(8),names)
    for i in range(8):
        for j in range(8): ax.text(j,i,f'{corr.iloc[i,j]:.2f}',ha='center',va='center',color='white' if abs(corr.iloc[i,j])>.65 else '#142b45')
    fig.colorbar(im,ax=ax,fraction=.046,pad=.04)
    fig.suptitle('회귀 입력 8개 지표의 Pearson 상관',fontsize=19,weight='bold')
    fig.text(.08,.025,f'동일 주 분석 표본 · VIF 범위 {vif.VIF.min():.2f}–{vif.VIF.max():.2f} · 상관은 관련성·인과·탐지 성능의 검증이 아닙니다.',fontsize=10)
    fig.savefig(OUT/'02_상관분석.png',dpi=170); plt.close(fig)

if __name__=='__main__': main()
