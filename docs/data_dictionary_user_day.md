# `user_day_ldap_logon_email.csv` 컬럼 정의서

> 대상 파일: `user_day_ldap_logon_email.csv`
> 생성 코드: [build_user_day_ldap_logon_email.py](../src/pipelines/build_user_day_ldap_logon_email.py) (`data` 폴더에서 `python src/pipelines/build_user_day_ldap_logon_email.py`, 약 1.5분)
> 원본: `inputs/LDAP/2009-12.csv`, `logon.csv`, `email.csv`
> 작성일: 2026-09-19

## 개요

| 항목 | 값 |
|---|---|
| 행 | 로그인 활동일 기준 사용자×날짜 **330,452행** (사용자 1,000명) |
| 컬럼 | 34개 |
| 메일이 없는 날 | 0으로 채움 (`email.csv`는 원본의 약 50% 샘플이므로 0은 "기록 없음"으로 해석) |
| 포함하지 않은 것 | 기준선·z점수·점수, LDAP 퇴사 정보(미래 정보), `size`(의미 없음), http·device·file |


| 규칙 | 내용 |
|---|---|
| 계정 채널 | `from` = LDAP 등록 주소 → 회사 계정, 아니면 개인 계정 (대소문자 무시) |
| 도메인 구분 | 사내 `dtaa.com` / 경쟁사 6곳 / 웹메일 15곳 |
| 수신자 파싱 | `to`·`cc`·`bcc`를 `;`로 분리, 소문자, 메일 안에서 중복 제거 |
| 날짜 | 원본 시각의 날짜 부분 (시간대 변환 없음) |
| 야간 | 07시 이전 또는 19시 이후 |

## 1. 키·날짜 (6개)

| 컬럼 | 의미 |
|---|---|
| `user` | 사용자 ID |
| `date` | 날짜 (YYYY-MM-DD) |
| `weekday` | 요일 (0 = 월 ~ 6 = 일) |
| `is_weekend` | 주말이면 1 |
| `active_day_seq` | 사용자별 로그인 활동일 순번 (1부터) |
| `days_since_first` | 사용자의 첫 로그인 활동일부터 지난 달력 일수 |

## 2. LDAP (5개, 2009-12 기준)

기간 중 이름·직무·부서·팀·상사가 바뀐 사람이 없으므로 2009-12 파일 값을 모든 날짜에 붙였습니다.

| 컬럼 | 의미 | 비어 있는 행 |
|---|---|---|
| `role` | 직무 (42개) | 없음 |
| `functional_unit` | 기능 조직 | 692행 (2명) |
| `department` | 부서 | 4,844행 (14명) |
| `team` | 팀 | 43,304행 (127명) |
| `supervisor` | 상사 이름 | 346행 (1명, President) |

- 비어 있는 값은 **원본 LDAP에서도 비어 있습니다**. 이사·매니저·비서처럼 팀보다 상위 조직에 속한 사람은 팀이 없습니다.
- 팀 이름은 여러 조직에서 반복되므로, 팀을 구분하려면 `functional_unit` + `department` + `team`을 함께 씁니다.

## 3. logon (7개)

| 컬럼 | 의미 |
|---|---|
| `logon_cnt` | `Logon` 건수 |
| `logoff_cnt` | `Logoff` 건수 |
| `logon_pc_cnt` | `Logon`한 서로 다른 PC 수 |
| `other_pc_logon_cnt` | 본인 PC가 아닌 PC에 `Logon`한 건수. **본인 PC = `email.csv`에서 쓰는 PC** (사용자마다 1대) |
| `night_logon_cnt` | 야간(07시 이전·19시 이후) `Logon` 건수 |
| `first_logon_min` | 첫 `Logon` 시각 (자정부터 분, 예: 485 = 08:05) |
| `last_logoff_min` | 마지막 `Logoff` 시각 (자정부터 분) |

- `logon_cnt = 0`인 184행은 그날 `Logoff`만 있는 날입니다. 전날 로그인해 자정을 넘겨 로그아웃한 경우로 보이며, `first_logon_min`이 비어 있습니다.

## 4. email: 기존 행동지표 6개

[build_email_user_day_dataset.py](../src/pipelines/email_user_day/build_email_user_day_dataset.py)의 함수를 그대로 사용해, `email_user_day_baseline_dataset.csv`와 값이 같습니다.

| 컬럼 | 의미 |
|---|---|
| `email_cnt` | 메일 수 |
| `corp_ext_send_cnt` | 회사 계정으로 외부(사내 제외) 수신자에게 보낸 메일 수 |
| `new_ext_rcpt_cnt` | 처음 등장한 외부 수신자 주소 수 (사용자별, 데이터 시작부터 누적 기준) |
| `corp_ext_att_mail_cnt` | 회사 계정 + 외부 수신자 + 첨부 있는 메일 수 |
| `personal_att_mail_cnt` | 개인 계정 + 첨부 있는 메일 수 |
| `jobkw_mail_cnt` | 회사 계정 + 구직 키워드 12개 중 3개 이상 포함 메일 수 |

## 5. email: 추가 집계 (10개)

| 컬럼 | 의미 | 참고 |
|---|---|---|
| `corp_mail_cnt` | 회사 계정 메일 수 | `corp_mail_cnt + personal_mail_cnt = email_cnt` |
| `personal_mail_cnt` | 개인 계정 메일 수 | |
| `rcpt_cnt` | 수신자 수 합계 (메일마다 중복 제거 후 합산) | `= int + competitor + webmail` |
| `int_rcpt_cnt` | 사내(`dtaa.com`) 수신자 수 | 시나리오 3(사내 발송) 대응용 |
| `competitor_rcpt_cnt` | 경쟁사 6곳 수신자 수 | 시나리오 2(경쟁사 발송) 대응용 |
| `webmail_rcpt_cnt` | 웹메일 15곳 수신자 수 | |
| `att_mail_cnt` | 첨부가 있는 메일 수 | |
| `att_cnt` | 첨부 개수 합계 | |
| `bcc_mail_cnt` | BCC가 있는 메일 수 | |
| `night_mail_cnt` | 야간 메일 수 | |

## 6. 검증 결과

| 확인 항목 | 결과 |
|---|---|
| 행 수 / 중복 키 | 330,452행 / 0건 |
| `Logon` 합계 | 470,591 = 원본 470,591 |
| `Logoff` 합계 | 384,268 = 원본 384,268 |
| `email_cnt` 합계 | 1,314,400 = 원본 1,314,400 |
| `att_cnt` 합계 | 530,309 = 원본 530,309 |
| `bcc_mail_cnt` 합계 | 208,610 = 원본 208,610 |
| 회사 계정 비율 | 62.3% (LDAP 분석 결과와 같음) |
| `corp + personal = email_cnt` | 전체 행 성립 |
| `rcpt = int + competitor + webmail` | 전체 행 성립 (외부 도메인이 21개뿐임을 확인) |
| 기존 `email_user_day_merged.csv`와 비교 | 겹치는 8개 컬럼 330,452행 모두 일치 |

## 7. 사용 시 주의

- **기준선·점수는 없습니다.** 기준선은 당일 이전 데이터로만 계산해야 합니다.
- **점수 계산 대상 행**은 `active_day_seq > 10` 이고 `days_since_first >= 30`인 행입니다 (308,023행).
- **`other_pc_logon_cnt`의 본인 PC**는 전체 기간 `email.csv`에서 쓰는 PC입니다. 사용자마다 1대로 고정돼 있어 미래 정보 문제는 작지만, 엄격하게 하려면 당일 이전 로그인 기록으로 본인 PC를 다시 정할 수 있습니다.
- **logon 지표는 "확장 제안"**으로 표시합니다. 이메일 지표와 섞어 점수를 내면 이메일 지표의 효과를 따로 판단할 수 없습니다.
