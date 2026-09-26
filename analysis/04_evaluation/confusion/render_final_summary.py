"""Render the final report figure from verified current-policy evaluation tables."""
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import hashlib
import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
STEM='20260922_173942_최종_혼동행렬_시각화'
meta=json.loads((HERE/'evaluation_metadata.json').read_text(encoding='utf-8'))
assert hashlib.sha256((PROJECT_ROOT / "outputs/dashboard/scored.parquet").read_bytes()).hexdigest()==meta['source_score_sha256']
m=pd.read_csv(HERE/'confusion_metrics.csv')
decomp=pd.read_csv(HERE/'alert_decomposition.csv')
u=m.query("period == 'post' and channel == 'combined' and unit == 'user_any_alert'").iloc[0]
d=m.query("period == 'post' and channel == 'combined' and unit == 'user_day'").iloc[0]
dec=decomp.query("period == 'post' and channel == 'combined'").iloc[0]
plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':11})
fig,axes=plt.subplots(1,3,figsize=(17,8.5),gridspec_kw={'width_ratios':[1,1,1.1]})
fig.subplots_adjust(left=.085,right=.97,top=.76,bottom=.30,wspace=.53)
for ax,r,title,labels in [
    (axes[0],u,'사용자 혼동행렬 · 975명',['내부자','비내부자']),
    (axes[1],d,'사용자·일 혼동행렬 · 225,281일',['사건기간 안','사건기간 밖\n/ 비내부자'])]:
    values=np.array([[r.TP,r.FN],[r.FP,r.TN]],dtype=float)
    frac=values/values.sum(axis=1,keepdims=True)
    ax.imshow(frac,cmap='Blues',vmin=0,vmax=1)
    for i in range(2):
        for j in range(2):
            ax.text(j,i,f"{[['TP','FN'],['FP','TN']][i][j]}\n{int(values[i,j]):,}\n{frac[i,j]:.1%}",ha='center',va='center',
                    color='white' if frac[i,j]>.55 else '#17334d',fontsize=15,linespacing=1.6)
    ax.set_xticks([0,1],['경보 있음','경보 없음']); ax.set_yticks([0,1],labels)
    ax.tick_params(length=0,pad=9)
    ax.set_title(title,pad=18,fontsize=13,weight='bold')
    ax.set_xlabel('예측',labelpad=10)
    ax.set_xticks([.5],minor=True); ax.set_yticks([.5],minor=True); ax.grid(which='minor',color='white',linewidth=3)
    ax.tick_params(which='minor',length=0)
    for spine in ax.spines.values(): spine.set_visible(False)
    caption=(f'기간 중 경보를 받은 내부자 {int(u.TP)}명\n정밀도 {u.precision:.2%} · 사용자 경보 재현율 {u.recall:.2%}' if ax==axes[0] else
             f'사건기간 안 경보 {int(d.TP)}일\n정밀도 {d.precision:.2%} · 일 단위 재현율 {d.recall:.2%}')
    ax.text(.5,-.26,caption,ha='center',va='top',transform=ax.transAxes,fontsize=10,linespacing=1.8)
ax=axes[2]
counts=[int(dec.incident_detected_users),int(dec.outside_only_insiders),int(u.FN)]
colors=['#218577','#d2973a','#8d99a8']
left=0
for value,color in zip(counts,colors):
    ax.barh([0],value,left=left,color=color,height=.35)
    ax.text(left+value/2,0,str(value)+'명',ha='center',va='center',color='white',weight='bold',fontsize=13)
    left+=value
ax.set_xlim(0,70); ax.set_ylim(-.75,.75); ax.axis('off')
ax.set_title('실제 사건 탐지 · 내부자 70명',pad=18,fontsize=13,weight='bold')
for y,color,text in zip([.27,.15,.03],colors,['사건기간 안 탐지: 29명 (41.43%)','사건기간 밖에서만 경보: 12명','평가기간 전체 무경보: 29명']):
    ax.text(0,y,'● '+text,transform=ax.transAxes,color=color,fontsize=11,va='center')
ax.text(0,-.19,'사건기간 미탐 = 12 + 29 = 41명\n비내부자 오탐 = 299 / 905명 (33.04%)',transform=ax.transAxes,fontsize=11,linespacing=1.8)
fig.text(.045,.945,'통계 기반 내부자 탐지 모델 | 최종 성능평가',fontsize=23,weight='bold',color='#17334d')
fig.text(.045,.873,'email-review-v2.2 · 이메일 주의 이상 OR 로그온 경보 · 외부 발송/첨부는 최댓값 반영\n2010-06-01 ~ 2011-05-17 · 내부자 70명 / 비내부자 905명',fontsize=11,color='#526273')
fig.text(.045,.055,'왼쪽: 사건기간 밖 경보도 사용자 양성 예측에 포함. 가운데: 사건기간을 하루 단위 대리 정답으로 사용.\n색 농도는 각 행 내 비율이며, 기존 정답을 활용한 사후 평가로 독립 검증 성능이 아닙니다.',fontsize=10,color='#526273')
for ext in ['png','svg']: fig.savefig(ROOT/(STEM+'.'+ext),dpi=180)
plt.close(fig)
print(STEM)
