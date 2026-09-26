from pathlib import Path
import json
import pandas as pd

P=Path(__file__).resolve().parent
main=pd.read_csv(P/'main_or.csv'); vif=pd.read_csv(P/'vif.csv')
all_results=pd.read_csv(P/'all_models_or.csv')
diag=pd.read_csv(P/'model_diagnostics.csv')
pearson=pd.read_csv(P/'correlation_pearson.csv',index_col=0)
spearman=pd.read_csv(P/'correlation_spearman.csv',index_col=0)

def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
        ['| '+' | '.join(map(str,row))+' |' for row in rows])

def pformat(p): return f'{p:.2e}' if p<.001 else f'{p:.4f}'

or_table=table(['지표','조정 OR','95% 신뢰구간','군집 보정 p','BH q','VIF'],[
    [r.label,f'{r.OR:.3f}',f'{r.CI_low:.3f}–{r.CI_high:.3f}',pformat(r.p_cluster),pformat(r.q_BH),
     f'{vif.set_index("term").loc[r.term,"VIF"]:.3f}'] for r in main.itertuples() if r.term!='const'])
pairs=[('corp_ext_send_cnt_z','corp_ext_att_mail_cnt_z'),('other_pc_logon_cnt_z','night_logon_cnt_z'),('new_ext_rcpt_cnt_z','personal_att_mail_cnt_z')]
labels=vif.set_index('term').label.to_dict()
corr_table=table(['지표 쌍','Pearson','Spearman'],[[labels[a]+' ↔ '+labels[b],f'{pearson.loc[a,b]:.3f}',f'{spearman.loc[a,b]:.3f}'] for a,b in pairs])
names={'main':'주 분석: 부호 있는 z','positive_z':'IF 방식: max(z,0)','without_jobkw':'구직 키워드 제외',
       'exclude_scenario2':'시나리오 2 사용자 전체 제외','month_supported_unadjusted':'2011-04까지, 월 미보정',
       'month_adjusted':'2011-04까지, 월 보정','hinge_at_zero':'z=0 기울기 분리'}
fit_table=table(['모형','사용자·일','양성일','McFadden pseudo-R²'],[
    [names[r.model],f'{r.n:,}',f'{r.positive_days:,}',f'{r.mcfadden:.5f}'] for r in diag.itertuples()])
sens=[]
for model in ['main','positive_z','month_adjusted']:
    for term in ['corp_ext_send_cnt_z','night_logon_cnt_z','jobkw_mail_flag']:
        r=all_results.loc[all_results.model.eq(model)&all_results.term.eq(term)].iloc[0]
        sens.append([names[model],labels[term],f'{r.OR:.2f}',f'{r.CI_low:.2f}–{r.CI_high:.2f}'])
hinge=pd.read_csv(P/'hinge_positive_slopes.csv')
for term in ['corp_ext_send_cnt_z','night_logon_cnt_z']:
    r=hinge.set_index('term').loc[term]
    sens.append(['기울기 분리: z>0 구간',labels[term],f'{r.OR:.2f}',f'{r.CI_low:.2f}–{r.CI_high:.2f}'])
sens_table=table(['모형','지표','OR','95% CI'],sens)

text=f'''# 사용자·일 사건기간 관련성: 상관·VIF·로지스틱 회귀

작성: 2026-09-23. 기존 점수 정책과 Isolation Forest를 변경하지 않은 사후 탐색 분석.

**구직 키워드와 야간 로그온의 양의 관련성은 여러 모형에서 유지된다. 다중공선성은 크지 않다. 그러나 외부 발송은 모형 형태에 따라 방향이 바뀌므로 단일 선형 로지스틱 결과로 지표를 삭제하거나 가중치를 정하면 안 된다.**

## 1. y 정의와 분석 범위

- 단위: 관측된 사용자·일. 경보가 발생하지 않은 행도 포함한다. 없는 날짜를 0으로 채우지 않는다.
- 주 분석 기간: **2010-06-01~2011-05-17**, 기존 점수 보정기간 이후.
- 대상: **225,281 사용자·일 / 975명**. 과거 이력이 충분해 `is_scored=1`인 행만 사용한다.
- y=1: `labels/answers/insiders.csv`의 dataset 4.2 정답 사용자가 사건 시작일~종료일 안에 해당하는 날. 날짜 양 끝 포함.
- y=0: 사건기간 밖 정답 사용자와 비내부자의 나머지 관측일.
- 양성: **1,364일 / 70명**, 전체 행의 **0.6055%**. 음성 223,917일.
- 시나리오별 양성일: 1번 156일, 2번 1,188일, 3번 20일. 시나리오 2가 양성일의 **87.10%**를 차지한다.

이 y는 **사건기간 대리 라벨**이다. 사건기간 안 모든 날짜에서 유출 이벤트가 확인되었다는 뜻이 아니고, y=0도 건별 정상 확인을 뜻하지 않는다. CERT 내부자 시나리오는 이메일 외부유출만을 대상으로 하지 않는다.

전체 원자료는 330,452행이며 기준선 준비 미충족 22,429행은 전체기간에서 제외 대상이다. 준비조건 충족 308,023행 중 보정기간 82,742행을 이번 주 분석에서 추가 제외했다. 보정기간을 분리했지만, 이미 정답을 검토한 프로젝트이므로 독립 홀드아웃은 아니다.

## 2. 입력 변수와 추정 방법

건수형 6개는 저장된 부호 있는 개인 기준선 z를 사용했다. 구직 키워드는 `jobkw_mail_flag`, 새로운 야간 메일은 `night_mail_flag=1 & night_mail_past30=0`이다. 사내 수신자는 현재 지표에서 제외되어 있어 넣지 않았다.

```text
logit(P(y=1)) = 절편 + 외부발송_z + 신규외부수신자_z + 외부첨부_z
                + 개인첨부_z + 다른PC로그온_z + 야간로그온_z
                + 구직키워드_flag + 새로운야간메일_flag
```

식의 각 항에는 별도 회귀계수가 곱해진다. 기존 점수·총점·등급·IF 출력·사용자 ID는 설명변수에 넣지 않았다. 사용자 ID는 군집 표준오차 계산에만 사용했다.

- 추정: **무벌점 로지스틱 최대우도**, 사용자별 군집 강건 표준오차(CR1).
- 공분산: `H^(-1) [Σ 사용자별 score합 × score합ᵀ] H^(-1)`에 `G/(G−1) × (N−1)/(N−K)` 보정. H는 로지스틱 관측 정보행렬이다.
- p와 95% CI: 사용자 군집 수−1, 주 분석 자유도 **974**의 t 기준.
- 8개 주 지표의 다중검정 참고용 **BH q값** 병기. 모형을 반복 탐색한 전체 과정까지 보정한 확증적 p값은 아니다.
- 군집 보정은 표준오차·신뢰구간을 바꾸며, 사용자 고정효과나 랜덤효과를 추가하는 것과 다르다. 직무·개인 특성 등 누락 교란을 제거하지 않는다.
- z는 `(당일−과거평균)/max(과거표준편차,1)`이다. OR는 **보정 z 1단위 증가** 기준이며 모든 행에서 정확한 개인 표준편차 1 증가가 아니다. 플래그 OR는 0→1 기준이다.
- 이 회귀는 당일 자료와 당일 사건기간의 관련성을 분석한다. 미래 사건 사전예측이나 사건 원인 분석이 아니다.

## 3. 상관분석과 VIF

상관은 회귀와 동일한 225,281행·입력 변환에서 계산했다. 따라서 전체기간을 사용한 기존 상관분석과 소폭 다르다.

{corr_table}

**VIF는 1.001~1.539**다. 주 모형에서 VIF 때문에 제외할 변수는 없다. 낮은 VIF는 모형의 형태나 지표의 탐지 유용성이 타당하다는 증명은 아니다. 또한 기존 점수에서 외부 발송/첨부의 max 처리와 회귀의 공선성 진단은 서로 다른 문제다.

![회귀 입력 상관](02_상관분석.png)

## 4. 주 모형: OR와 95% 신뢰구간

다른 7개 지표를 함께 고려한 관련성이다. 각 지표의 1단위 의미가 다르므로 OR 크기만으로 중요도 순위를 매기지 않는다.

{or_table}

![주 모형 OR와 신뢰구간](01_OR_신뢰구간.png)

### 구직 키워드: 강한 관련성이지만 시나리오 2에 한정된 근거

주 모형 OR **416.03 [284.85, 607.60]**. 구직 키워드가 있는 날은 사건기간에서 123/1,364일(9.02%), 사건기간 밖에서 66/223,917일(0.0295%)이다. 양성 123일은 **전부 시나리오 2의 30명**에서 발생했다. 완전분리는 아니지만 매우 강한 시나리오 신호다.

이는 기존 IF의 개선이 구직 키워드에 집중되었다는 관찰과 일치한다. 다만 구직 키워드가 있으면 실제 유출 확률이 416배이거나 모든 내부자 시나리오에 유효하다는 의미는 아니다. 정상 시나리오 생성 방식과 악성 시나리오 정의의 영향을 받는 합성 데이터의 결과다.

### 야간 로그온: 여러 설정에서 양의 관련성 유지

주 모형 OR **3.23 [2.17, 4.80]**. 양수 z 모형은 **4.76 [2.81, 8.06]**, 증가/감소 구간을 나눈 모형의 양수 구간은 **5.02 [2.77, 9.11]**이다. 월 보정에서도 **3.14 [2.13, 4.62]**로 유지된다.

시나리오 2 사용자 전체를 제외하면 OR **22.68 [16.01, 32.11]**이다. 이 값은 다른 모집단·기저율·다른 입력 구성의 결과이므로 주 모형보다 효과가 몇 배 강해졌다고 직접 비교하지 않는다. 시나리오 1·3의 관련성을 확인하는 보조 근거다.

### 외부 발송: 주 모형의 음의 OR를 보호효과로 읽으면 안 됨

주 모형은 **0.86 [0.77, 0.96]**이지만, 양수 z 모형은 **1.07 [0.91, 1.25]**, 기울기 분리 모형의 양수 구간은 **1.35 [1.08, 1.68]**이다. 방향과 유의성이 모형 형태에 민감하다.

따라서 “외부 발송이 많을수록 안전하다” 또는 “불필요한 지표다”라는 결론은 근거가 없다. 평소보다 감소한 구간과 증가한 구간에 하나의 기울기를 강제하는 것이 부적절할 수 있다.

### 다른 PC 로그온: 음의 조건부 관련성을 탐지 규칙 반전에 사용하면 안 됨

주 모형 **0.63 [0.46, 0.87]**은 야간 로그온 등 다른 변수를 고정한 조건부 관련성이다. 야간 로그온과의 공통 변동, 시나리오 구성, 개인별 업무 차이 등의 영향을 분리한 인과효과는 아니다. 이 결과만으로 위험점수를 낮추거나 기존 지표를 제거하지 않는다.

### 나머지 지표: 무효 판정이 아닌 불확실성

신규 외부 수신자·외부 첨부·개인계정 첨부·새로운 야간 메일은 주 모형의 95% CI가 1을 포함한다. 특히 새로운 야간 메일은 양성에서 **2일/2명**만 관측되어 CI가 **0.25~3.90**으로 넓다. “관련성이 없다”보다 “현재 라벨과 모형으로 명확히 추정하기 어렵다”가 적절하다. 외부 첨부는 양수 z 모형에서 결과가 달라져 형태 민감성도 있다.

## 5. 모형 형태와 시나리오 민감도

{sens_table}

6개 z에 `max(z,0)` 항을 추가해 감소 구간과 증가 구간의 기울기를 구분했다. 기울기 차이 6개 항의 사용자 군집 강건 공동 Wald 검정은 **F(6,974)=5.245, p=0.00002495**다. 하나 이상의 지표에 대해 전 구간 동일 기울기 가정이 맞지 않을 가능성을 보여준다. 주 모형의 단일 OR를 최종 확정 수치로 쓰기보다 이 민감도와 함께 제시해야 한다.

`hinge_at_zero_or.csv`에서 건수형 원항의 계수는 **z<0 구간 기울기**, 추가항은 **기울기 차이**이다. 증가 구간 OR는 두 계수를 합하고 공분산까지 반영한 `hinge_positive_slopes.csv`를 사용한다. 이 모형도 양수 구간 내부의 모든 비선형성이나 상호작용을 검증한 것은 아니다.

시나리오 2 제외 분석은 해당 30명의 모든 행을 제거했다. 남은 40명의 양성일은 176일이며, 구직 키워드와 새로운 야간 메일은 양성 지원이 0이라 해당 보조 모형에서만 제외했다. 주 모형의 변수 삭제를 뜻하지 않는다.

월 고정효과를 전체기간에 적용하면 **2011년 5월 양성일이 0**이어서 5월 계수가 음의 무한대로 향하는 분리가 발생했다. 해당 시도의 계수·p는 채택하지 않았다. 주 분석은 5월을 유지하고, 월 보정 민감도만 **2010-06~2011-04의 215,733행**으로 제한했다. 같은 표본의 월 미보정 모형도 함께 저장해 표본 변경과 월 보정 영향을 구분했다. 이 조치는 첫 실행 후 진단에 따른 변경이다.

## 6. pseudo-R²와 반복관측 보정의 의미

{fit_table}

주 모형의 **McFadden pseudo-R²=0.068996**이다. 분산 설명률 6.9%도 정확도 6.9%도 아니다. working-independence log-likelihood를 이용한 기술적 적합도 참고치이며, 사용자 군집 보정을 했다고 likelihood 자체가 반복관측의 결합분포로 바뀌지는 않는다.

같은 표본에서 구직 키워드를 제외하면 **0.006269**로 낮아진다. 주 모형의 적합도 개선이 해당 신호에 많이 의존한다는 근거다. 시나리오 2 제외나 기간 제한처럼 y 분포와 표본이 바뀐 모형의 pseudo-R²를 단순 우열 비교하지 않는다. 월 보정 모형의 pseudo-R²에는 월 효과의 적합도도 포함된다.

반복관측 보정은 실질적인 차이를 만든다. 야간 로그온의 표준오차는 독립 가정 0.1042에서 군집 보정 **0.2021**로 커졌고, p는 약 2.54e-29에서 **9.34e-09**로 바뀌었다. 표본 수 225,281을 독립 관측 수처럼 취급해서는 안 된다. 반대로 군집 보정이 모든 지표의 표준오차를 반드시 키우는 것은 아니다.

## 7. 프로젝트에 반영할 판단

1. **통계분석 추가는 유용했다.** 지표 중복은 심하지 않지만 시나리오 2 편중과 회귀 형태 민감성이 확인되었다.
2. **구직 키워드와 야간 로그온의 역할을 분리해 설명한다.** 구직 키워드는 시나리오 2 중심, 야간 로그온은 다른 시나리오의 관련성을 보완한다.
3. **p값만으로 지표를 삭제하거나 회귀계수를 기존 점수 가중치로 옮기지 않는다.** 기존 탐지 목적은 극단적인 이상행동 선별이고 이 분석은 사건기간 전체의 평균적인 조건부 관련성이다.
4. **발표 자료에는 OR·95% CI와 형태 민감도를 함께 넣는다.** 특히 외부 발송의 방향 변화와 새로운 야간 메일의 양성 지원 부족을 생략하지 않는다.
5. 회귀를 실제 탐지기로 채택하려면 새 미사용 데이터에서 PR-AUC, 동일 조사량 기준 정밀도·재현율, 확률 보정 등을 별도 검증해야 한다. 이번 분석은 이를 수행한 결과가 아니다.

군집 표준오차는 사용자 간 독립을 전제로 한다. 같은 날의 조직 공통 충격, 직무 차이, 사용자별 관측기간 길이, 시간에 따른 기준선 적응은 추가 한계다. 긴 사건기간의 사용자가 양성일을 많이 제공하므로 사용자마다 동일한 가중치를 둔 분석과도 다르다. 이번에 사용자·직무 고정효과, 전체적인 비선형·상호작용, 사용자 군집 부트스트랩을 모두 검증한 것은 아니다.

## 8. 검증과 재현

- 사용자·일 중복 없음, 설명변수 유한값, 설계행렬 full rank 확인.
- 기존 `post_day_predictions.csv`의 y와 **225,281행 전부 일치**.
- 채택한 7개 모형 모두 수렴하고 scaled score 최대 절댓값 <1e-4.
- 주 모형 계수를 sklearn 무벌점 Newton-Cholesky와 독립 비교: 최대 차이 **2.67e-09**.
- 사용자별 score 합을 NumPy와 pandas 두 방식으로 대조; VIF를 상관행렬 역행렬과 보조회귀로 대조.
- OR/상관 그림의 한글·잘림·수치를 시각 점검.
- 현재 Python 환경에 statsmodels가 없어 NumPy/SciPy로 무벌점 MLE와 CR1 sandwich를 구현했다. sklearn은 계수 독립 검산에 사용했으며, 벌점 모형의 계수에 일반 p값을 붙이지 않았다.
- 입력 파일 SHA-256, 패키지 버전, 수렴 진단은 `analysis_metadata.json`에 저장.

작업공간 루트에서 다음 명령으로 재현한다.

```powershell
python 'experiments/20260923_로지스틱_통계분석/analyze.py'
python 'experiments/20260923_로지스틱_통계분석/write_report.py'
```

주요 산출물: [주 모형 OR](main_or.csv), [전체 모형 OR](all_models_or.csv), [VIF](vif.csv), [Spearman](correlation_spearman.csv), [모형 진단](model_diagnostics.csv), [시나리오별 지원](feature_support_by_scenario.csv), [증가 구간 OR](hinge_positive_slopes.csv), [재현 코드](analyze.py). `analysis_rows.csv`는 실제 분석 표본과 y·X의 행별 원장이다.

방법 참고: [statsmodels 군집 sandwich 구현](https://www.statsmodels.org/stable/_modules/statsmodels/stats/sandwich_covariance.html), [VIF 정의](https://www.statsmodels.org/stable/generated/statsmodels.stats.outliers_influence.variance_inflation_factor.html), [McFadden pseudo-R² 정의](https://www.statsmodels.org/stable/generated/statsmodels.discrete.discrete_model.LogitResults.prsquared.html). 이 문서들은 방법 참고이며 이번 계산을 statsmodels로 실행했다는 뜻은 아니다.
'''
(P/'분석결과.md').write_text(text,encoding='utf-8')
print('Report saved:',P/'분석결과.md')
