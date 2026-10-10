# 보안 담당자용 대시보드

### ▶ [배포된 대시보드 보기](https://siemcloud-qc3nzy5td7toothhq4cgdx.streamlit.app/user)

확정 모델 `email-review-v2.2`의 점수 결과를 보여주는 Streamlit 앱입니다. "오늘 누구를, 왜 조사해야 하는가"에 답하는 것이 목표입니다.

| 메뉴 | 구성 |
|---|---|
| 대시보드 | KPI 4개(직전 같은 길이 기간 대비), 조사 우선순위 TOP 10, 선택 사용자 근거, 위험 수준 분포, 일별 경보 추이 |
| 위험도 랭킹 | 사용자별 최고 등급·경보일 수·첫/최근 경보일, 채널·등급 필터, CSV 내보내기 |
| 사용자 분석 | 채널별 점수·등급, 선정 이유, 8개 지표 근거표(오늘 값·평소 평균·z·경계), 날짜별 점수 변화, 조사 근거 ZIP |
| 점수·등급 기준 | 확정 정책, z 경계, 데이터 출처 |

## 설계 원칙

- 확정 산출물(`scored.parquet`, `metadata.json`, `link_events.parquet`)을 읽기 전용으로 씁니다. 불러올 때 저장된 점수를 확정 정책으로 다시 계산해 대조합니다.
- 이메일 점수와 로그온 점수는 더하지 않습니다. 조사 대상은 이메일 주의 이상 OR 로그온 경보입니다.
- 정답(내부자) 자료는 연결하지 않습니다. 등급 색상은 항상 등급 글자와 함께 표시합니다.

## 로컬 실행

입력 데이터는 라이선스상 저장소에 포함하지 않았습니다. [data/README.md](../data/README.md)대로 원본을 받고 `src/scoring/prepare_data.py`를 실행한 뒤, 생성된 파일을 `dashboard/data/`에 둡니다.

```bash
cd dashboard
streamlit run app.py          # http://127.0.0.1:8503
python test_overview.py       # 화면 렌더링·수치 검수 테스트
```
