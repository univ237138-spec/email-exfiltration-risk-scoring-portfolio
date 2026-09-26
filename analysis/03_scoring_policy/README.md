# 03. 점수와 경보 정책

정답 없이 z를 점수로 바꾸는 경계와 경보 정책을 정했습니다.

- **개인 기준선:** `z = (오늘 값 − 직전 30활동일 평균) / max(표준편차, 1)`
- **경계:** 보정기간(2010-01~05) z 분포의 상위 1% / 0.25% / 0.05% → 1 / 2 / 3점. 이후 고정합니다.
- **이메일 등급:** 관심 ≥ 2 · 주의 ≥ 3 · 위험 ≥ 5. 외부 발송과 외부 첨부는 큰 값 하나만 반영합니다.
- **로그온 경보:** 두 지표의 최댓값이 3점이거나, 2점이면서 z ≥ 1.9443
- **조사 대상:** 이메일 주의 이상 OR 로그온 경보

| 파일 | 내용 |
|---|---|
| [final_scoring_indicators.md](final_scoring_indicators.md) | 확정 지표 8개, 경계값, 점수 계산과 등급 |
| [normal_vs_anomaly_rule.md](normal_vs_anomaly_rule.md) | 정답 없이 "이상"을 정의하는 세 가지 방식과 지표별 적용 |
| [score_boundary_calibration.md](score_boundary_calibration.md) | 경계 보정 기준과 경보량 |
| [why_not_label_fitted_weights.md](why_not_label_fitted_weights.md) | 가중치를 정답에 맞추지 않은 이유 |
| [indicator_handling_order.md](indicator_handling_order.md) | 지표 처리 방식을 정하는 판단 순서 |

점수 계산 코드: [src/scoring/scoring.py](../../src/scoring/scoring.py)
