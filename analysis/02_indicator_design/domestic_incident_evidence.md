# 실제 사례로 본 이메일 내부자 유출 행동

> 작성일: 2026-09-21
> 목적: 이메일 유출 탐지 지표가 실제 사고의 행동과 맞는지 확인할 근거 정리
> 관련 문서: `점수지표_9개_상세설명.md`, `핵심지표_5개_선정과_파생과정.md`

## 요약

실제 사고에서 반복되는 이메일 유출 행동은 7가지입니다.

| # | 행동 | 대표 사례 | 대응 지표 |
|---|---|---|---|
| 1 | 회사 메일에서 **본인 개인 메일로 첨부 전송** | 삼성전자 수석연구원, 삼성엔지니어링, CFPB, Anthem 협력사 | `corp_ext_att_mail_cnt` |
| 2 | **퇴사·이직 직전**에 집중 | 삼성 두 사건, 로펌 퇴사자, Omni Logistics, CERT 통계 | LDAP 퇴사일 (지표 없음) |
| 3 | **짧은 기간에 대량·반복 발송** (여러 통으로 나눠 보냄) | CFPB 14통, 로펌 퇴사자, 삼성 100종 | `corp_ext_send_cnt`, `corp_ext_att_mail_cnt` z점수 |
| 4 | **경쟁사·새 회사 사람에게 직접 발송** | Genentech→JHL, Omni→Expedite | `new_ext_rcpt_cnt` |
| 5 | **가족 등 제3자 개인 메일로 발송** (부주의형) | Boeing | `new_ext_rcpt_cnt`, `corp_ext_att_mail_cnt` |
| 6 | **내용 은닉** (사진 속에 숨김, 암호화) | GE 엔지니어 스테가노그래피 | 개수 지표로는 못 잡음 |
| 7 | **구직·이직 준비 흔적** | 삼성·삼성엔지니어링 (외국 업체 이직 목적) | `jobkw_mail_cnt` |

---

## 1. 회사 메일에서 본인 개인 메일로 전송 (가장 흔함)

| 사례 | 행동 | 근거 |
|---|---|---|
| **삼성전자 전 수석연구원** (한국) | 외국 반도체 업체로 이직하려고 3~6월에 D램 적층조립기술 등 **국가핵심기술 13건, 영업비밀 100종을 개인 이메일로 전송** | [이데일리](https://edaily.co.kr/News/Read?mediaCodeNo=257&newsId=02870006635712568) |
| **삼성엔지니어링 전 직원** (한국) | 중국 컨설팅사 이직을 앞두고 초순수시스템 설계 도면·제어 알고리즘을 **개인 이메일로 발송하거나 출력**. 2026-05 대법원이 산업기술 유출로 인정 | [경향신문](https://www.khan.co.kr/article/202605141523001), [세계일보](https://segye.com/newsView/20260514515057) |
| **CFPB 직원** (미국 금융감독기관) | 소비자 약 25.6만 명의 이름·계좌번호가 든 스프레드시트를 **개인 메일로 14통에 걸쳐 전송**. 내부 점검으로 발견 | [The Record](https://therecord.media/cfpb-employee-sent-confidential-information-to-personal-email), [Roll Call](https://rollcall.com/2023/04/19/cfpb-employee-sent-data-of-250000-customers-to-personal-email/) |
| **Anthem 협력사 LaunchPoint 직원** | 가입자 1.8만 명의 Medicare ID·주민번호가 든 파일을 **개인 메일로 전송**. **10개월 뒤에야** 발견 | [Healthcare IT News](https://www.healthcareitnews.com/news/anthem-insider-theft-exposes-data-18000-medicare-members), [CNBC](https://www.cnbc.com/2017/07/31/new-anthem-data-breach-by-contractor-affects-more-than-18000-enrollees.html) |
| **Wells Fargo 직원** | 고객 정보를 **개인 계정으로 전송**해 해고, 고객에게 유출 통지 | [HALOCK](https://www.halock.com/bank-employee-leads-to-data-breach-for-wells-fargo/) |

**시사점:** 실제 사고의 대부분은 "회사 계정 → 외부 주소(본인 개인 메일)"로 파일을 첨부해 보내는 형태입니다. 프로젝트의 `corp_ext_att_mail_cnt`가 가장 직접 대응합니다.

## 2. 퇴사·이직 직전에 집중

| 근거 | 내용 |
|---|---|
| **CERT(카네기멜런) 연구** | 지식재산 탈취 내부자 대부분은 **사직 전후 30일(총 60일) 안에** 최소 일부를 빼냈음. 네트워크를 쓴 경우 **대부분이 이메일과 VPN** | [SEI 블로그](https://www.sei.cmu.edu/blog/insider-threat-deep-dive-theft-of-intellectual-property/), [CERT Common Sense Guide 5판 (PDF)](https://archive.dni.gov/files/NCSC/documents/nittf/20180209-CERT-Common-Sense-Guide-Fifth-Edition.pdf), [InformIT 요약](https://www.informit.com/articles/article.aspx?p=1830484&seqNum=8) |
| **Proofpoint 로펌 사례** | 퇴사자가 **근무 마지막 날** 대량의 민감 자료를 개인 메일로 첨부 발송. "짧은 기간에 민감 자료 발송량과 빈도가 늘어나는 전형적 패턴" | [Proofpoint 블로그](https://www.proofpoint.com/us/blog/insider-threat-management/data-exfiltration-caused-by-departing-employee-at-law-firm) |
| **Proofpoint 2024 보고서** | 클라우드 환경의 비정상 파일 유출 중 **87%가 퇴사 예정자** 소행 | [Proofpoint 보도자료](https://www.proofpoint.com/us/newsroom/press-releases/proofpoints-inaugural-data-loss-landscape-report-reveals-careless-employees) |
| **Omni Logistics v. Wells** (2025, 미국 민사) | 영업이사가 재직 중 인수 관련 기밀을 **이직할 회사(Expedite Express) 메일 계정으로 전달** | [Farella Braun + Martel](https://www.fbm.com/publications/the-classic-email-to-self-as-trade-secret-misappropriation/) |

**시사점:** LDAP에서 사용자가 사라지는 월(퇴사 시점)을 기준으로 "퇴사 전 N일" 구간에 가중치를 주는 것이 실제 사례와 연구 모두에 맞습니다. 현재 지표에는 이 시간 요소가 없습니다.

## 3. 짧은 기간에 대량·반복 발송

- CFPB 직원은 한 번이 아니라 **14통으로 나눠** 보냈습니다.
- 삼성 사건은 **몇 달에 걸쳐 100종 이상**을 보냈습니다.
- Proofpoint는 6개월 평소 패턴 대비 **발송량·빈도 급증**으로 탐지했습니다.

**시사점:** 평소 대비 튐 정도를 보는 z점수 방식(`_z`)이 이 행동을 잡는 방식과 같습니다. 파일 크기가 크면 여러 통으로 나누는 경향이 있으므로 하루 단위뿐 아니라 **며칠 누적**도 볼 가치가 있습니다.

## 4. 경쟁사·새 회사 사람에게 직접 발송

| 사례 | 행동 | 근거 |
|---|---|---|
| **Genentech → JHL Biotech** | Genentech 직원 Xanthe Lam이 기밀 문서를 내려받아 **이미 JHL로 옮긴 동료에게 3차례 이메일로 전송**, 이후에도 요청받을 때마다 추가 전송 | [CSO Online](https://www.csoonline.com/article/572543/jhl-biotechs-theft-of-genentech-data-holds-lessons-for-infosec.html), [미 법무부](https://www.justice.gov/usao-ndca/pr/former-genentech-employees-charged-theft-trade-secrets) |
| **삼성엔지니어링** | 함께 이직한 전 삼성디스플레이 직원의 **부탁을 받고** 운전 매뉴얼 전달 | [경향신문](https://www.khan.co.kr/article/202605141523001) |

**시사점:** 평소 주고받지 않던 외부 주소가 새로 등장하는 것이 신호입니다. `new_ext_rcpt_cnt`가 대응합니다.

## 5. 가족 등 제3자 개인 메일로 발송 (부주의형)

- **Boeing (2016)**: 직원이 엑셀 서식 문제를 도움받으려고 **배우자 개인 메일로** 스프레드시트를 보냄. 숨긴 열에 직원 3.6만 명의 주민번호·생년월일이 들어 있었음. 약 7주 뒤 발견.
  - 근거: [GeekWire](https://www.geekwire.com/2017/personal-data-36000-boeing-employees-put-risk-employee-emails-info-spouse/), [Threatpost](https://threatpost.com/boeing-notifies-36000-employees-following-breach/123942/)

**시사점:** 악의가 없어도 행동 데이터상으로는 유출과 똑같이 보입니다. 오탐이 아니라 **실제 위험 사례**로 다뤄야 합니다.

## 6. 내용 은닉 (스테가노그래피·암호화)

- **GE 엔지니어 Xiaoqing Zheng (2018)**: 터빈 기술 파일을 **석양 사진 안에 숨겨** 본인 개인 메일(Hotmail)로 보냄. 2022년 유죄, 2023년 징역 2년.
  - 근거: [미 법무부 유죄 발표](https://www.justice.gov/archives/opa/pr/former-ge-power-engineer-convicted-conspiracy-commit-economic-espionage), [미 법무부 기소 발표](https://www.justice.gov/archives/opa/pr/former-ge-engineer-and-chinese-businessman-charged-economic-espionage-and-theft-ge-s-trade), [Security Boulevard](https://securityboulevard.com/2018/08/moonlighting-in-china-with-ges-intellectual-property/), [Schneier](https://www.schneier.com/blog/archives/2023/01/real-world-steganography.html)

**시사점:** 첨부 개수만 세는 지표로는 사진 한 장으로 보입니다. 다만 **"본인 개인 주소로 보낸다"는 행동 자체는 그대로**이므로 수신자 기준 지표로는 잡힙니다. 첨부 크기(`size`)가 평소 사진보다 큰지 보는 것이 보조 신호가 될 수 있습니다.

## 7. 구직·이직 준비 흔적

- 한국 두 사건 모두 **외국·중국 업체 이직이 목적**이었고, CERT도 이직 준비를 핵심 전조로 봅니다.
- `jobkw_mail_cnt`(구직 키워드 메일)가 이 동기를 담는 지표입니다.

---

## 프로젝트 지표에 주는 시사점

> **정정 (2026-09-21):** 아래 표의 "자기 자신에게 보내기" 지표는 이 데이터에 해당 메일이 0건이라 만들 수 없고, `size`는 첨부와 무관한 값이라 보조 신호로 쓸 수 없습니다. 상세는 `국내사례_기반_신규지표_판단.md` 6장을 참고하세요.

| 발견 | 현재 지표 상태 | 제안 |
|---|---|---|
| 실제 사고의 주 경로는 **회사 계정 → 본인 개인 주소** | `corp_ext_att_mail_cnt`가 외부 전체를 셈 | 이메일 데이터에서 사용자가 `from`으로 쓴 개인 주소를 모아, 회사 계정이 **그 주소로 보낸 메일**을 따로 세는 지표 검토 ("자기 자신에게 보내기") |
| **퇴사 전 30일**에 집중 (CERT) | 시간 요소 없음 | LDAP 퇴사월 기준 퇴사 전 구간 표시 또는 가중치 |
| **여러 통으로 나눠** 보냄 | 하루 단위 z점수 | 3~7일 누적 합계 z점수 추가 검토 |
| **은닉**하면 첨부 개수로는 안 보임 | 개수만 봄 | 첨부 크기(`size`) 평소 대비 z점수 보조 활용 |
| 개인 계정에서 보내는 경로(`personal_att_mail_cnt`) | 핵심 지표 | 실제 사례는 대부분 "회사 → 개인"이었고 "개인 계정에서 발송"은 드묾. 도메인 근거가 약하다는 기존 한계와 일치 |
