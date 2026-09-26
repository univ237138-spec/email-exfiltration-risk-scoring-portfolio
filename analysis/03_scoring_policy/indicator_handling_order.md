# 34개 컬럼을 어떤 방식으로 처리할지 정한 순서

> 대상: `user_day_ldap_logon_email.csv` (34컬럼) → `user_day_baseline_30.csv` (76컬럼)
> 작성일: 2026-09-20

## 요약

- 처리 방식은 **분포만으로 정하지 않았습니다.** 세 가지 기준을 순서대로 적용했습니다.
- ① 의미(행동인가) → ② 상관(겹치나) → ③ 분포(거의 항상 0인가)
- **분포가 결정한 것은 마지막 한 가지, z점수냐 규칙형이냐뿐입니다.**
- 여기에 더해 z점수 안에서도 표준편차 하한으로 분포 차이를 한 번 더 보정했습니다.

## 1. 판단 순서

```
34개 컬럼
  │
  ├─ ① 이게 "행동"인가?  ── 아니오(11개) → 키·날짜·LDAP: 그대로 둠
  │                          (user, date, weekday, is_weekend, active_day_seq,
  │                           days_since_first, role, functional_unit,
  │                           department, team, supervisor)
  ▼ 예 (23개)
  ├─ ② 다른 지표와 겹치나? ── 예(9개) → 제외·참고
  │                          중복 4개: competitor_rcpt_cnt, webmail_rcpt_cnt,
  │                                    att_mail_cnt, att_cnt
  │                          logon 5개: logon_cnt, logoff_cnt, logon_pc_cnt,
  │                                     first_logon_min, last_logoff_min
  ▼ 아니오 (14개)
  └─ ③ 분포가 어떤가?
        ├─ 거의 항상 0 (2개) → 규칙형 (_flag, _past30)
        └─ 값이 변함 (12개) → z점수 (_mu, _sd, _z)
```

| 단계 | 기준 | 근거의 성격 | 걸러진 컬럼 수 |
|---|---|---|---:|
| ① 행동인가 | 그날의 행동을 세는 값인가, 사람·날짜를 설명하는 값인가 | **의미** (분포와 무관) | 11 |
| ② 겹치나 | 포함 관계이거나 상관이 높은가 (0.85~0.999) | **상관관계** | 9 |
| ③ 분포 | 0인 날 비율이 거의 100%인가 | **분포** | 2 (규칙형) / 12 (z점수) |

## 2. ③단계의 실제 수치

점수 계산 대상 308,023행 기준입니다.

| 지표 | 0인 날 | 한 번도 없는 사용자 | 처리 |
|---|---:|---:|---|
| `jobkw_mail_cnt` | 99.9% | 890명 | **규칙형** |
| `night_mail_cnt` | 97.7% | 814명 | **규칙형** |
| `other_pc_logon_cnt` | 92.0% | 682명 | z점수 |
| `corp_ext_att_mail_cnt` | 88.4% | 204명 | z점수 |
| `personal_att_mail_cnt` | 78.5% | 201명 | z점수 |
| `bcc_mail_cnt` | 77.9% | 721명 | z점수 |
| `corp_ext_send_cnt` | 69.4% | 2명 | z점수 |
| `new_ext_rcpt_cnt` | 68.0% | 0명 | z점수 |
| `int_rcpt_cnt` | 24.9% | 0명 | z점수 |

### 경계는 고정된 숫자가 아닙니다

- "0인 날 X% 이상은 규칙형"처럼 기계적으로 정하지 않았습니다.
- 두 지표는 평소 값이 사실상 0이라 **"평소 대비"라는 개념이 성립하지 않아서** 규칙형으로 했습니다.
  - 구직 메일은 1,000명 중 890명이 한 번도 보낸 적이 없습니다. 이 사람들에게는 비교할 평소가 없습니다.
- **`other_pc_logon_cnt`(92%)는 경계에 가깝습니다.** 규칙형으로 바꿔도 이상하지 않습니다. 현재 z점수로 두었지만 z ≥ 2가 0.02%뿐이라 사실상 규칙형처럼 동작합니다.

## 3. z점수 안에서의 분포 대응: 표준편차 하한

```
z = (오늘 값 − 평균) ÷ max(표준편차, 1)
```

0이 많은 지표는 표준편차가 0에 가까워 1건만 발생해도 z가 폭발합니다. 하한이 이를 막습니다.

| 지표 | 하한이 적용된 비율 | 해석 |
|---|---:|---|
| `corp_ext_att_mail_cnt` | 99.8% | z는 사실상 "평소보다 몇 건 더" |
| `night_logon_cnt` | 96.7% | 〃 |
| `other_pc_logon_cnt` | 96.6% | 〃 |
| `corp_ext_send_cnt` | 92.5% | 〃 |
| `personal_att_mail_cnt` | 89.8% | 〃 |
| `new_ext_rcpt_cnt` | 85.0% | 〃 |
| `bcc_mail_cnt` | 80.2% | 〃 |
| `personal_mail_cnt` | 34.7% | 절반 이상은 실제 표준편차로 나눔 |
| `corp_mail_cnt` | 33.5% | 〃 |
| `email_cnt` | 33.0% | 〃 |
| `int_rcpt_cnt` | 5.8% | 거의 항상 실제 표준편차로 나눔 |
| `rcpt_cnt` | 1.1% | 〃 |

## 4. 남은 문제

현재는 **모든 z 지표에 같은 구간(z 2 / 3 / 4)**을 적용할 예정이라, 지표별로 점수가 나오는 빈도가 크게 다릅니다.

| 지표 | z ≥ 2 비율 |
|---|---:|
| `corp_ext_att_mail_cnt` | 0.19% |
| `personal_att_mail_cnt` | 1.43% |
| `corp_ext_send_cnt` | 1.58% |
| `new_ext_rcpt_cnt` | 2.18% |
| `int_rcpt_cnt` | **5.06%** |

같은 "z = 2"라도 지표마다 드문 정도가 다릅니다. 지표별 구간 경계를 따로 정하는 작업이 다음 단계에 필요합니다.

## 관련 문서

- [베이스라인_지표선정_근거.md](../02_indicator_design/indicator_selection_rationale.md): 34개 컬럼의 역할 구분과 지표별 선정 근거
- `베이스라인_설계안.md`: 기준선 계산 설계
- [user_day_baseline_30_컬럼정의서.md](../../docs/data_dictionary_baseline_30.md): 결과 76개 컬럼 정의와 검증 결과
