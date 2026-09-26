"""점수·등급 기준: 확정 정책과 정밀 경계, 데이터 출처."""
import pandas as pd
import streamlit as st

import services as sv
import ui


def render():
    c = ui.ctx()
    meta, prov = c.meta, c.provenance
    a, b = st.columns(2, gap="medium")
    with a, st.container(border=True, key="card_pol_email"):
        ui.card_title("이메일 점수 (지표 6개)")
        st.markdown(
            "- **z형 4개**: 회사계정 외부 발송 · 신규 외부 수신자 · 회사계정 외부 첨부 · 개인계정 첨부 — 각 0~3점\n"
            "- **규칙형 2개**: 구직 키워드 메일(회사메일 한 통에 키워드 3개 이상) 2점 · "
            "새로운 야간 메일(당일 야간 메일 + 직전 30활동일 야간 메일 0일) 1점\n"
            "- 외부 발송과 외부 첨부는 같은 행동의 중복이므로 **큰 점수 한 번만** 반영\n"
            "- 이메일 점수 = max(외부 발송, 외부 첨부) + 신규 외부 수신자 + 개인계정 첨부 + 구직 키워드 + 새로운 야간 메일")
        st.dataframe(pd.DataFrame({"등급": ["정상", "관심", "주의", "위험"], "이메일 점수": ["0~1점", "2점", "3~4점", "5점 이상"],
                                   "조사 대상": ["아니오", "아니오", "예", "예"]}), hide_index=True, width="stretch")
    with b, st.container(border=True, key="card_pol_logon"):
        ui.card_title("로그온 점수 (지표 2개)")
        st.markdown(
            "- **z형 2개**: 다른 PC 로그온 · 야간 로그온(19시 이상 또는 07시 미만) — 각 0~3점\n"
            "- 로그온 점수 = 두 점수 중 **최댓값** (0~3점)\n"
            f"- 2점이면 두 로그온 z의 최댓값이 **{meta.get('logon_z_cut', 1.9443)} 이상**일 때만 주의")
        st.dataframe(pd.DataFrame({"등급": ["정상", "관심", "주의", "위험"],
                                   "로그온 점수": ["0점", "1점, 또는 2점이면서 z 조건 미충족", "2점이면서 z 조건 충족", "3점"],
                                   "조사 대상": ["아니오", "아니오", "예", "예"]}), hide_index=True, width="stretch")
    with st.container(border=True, key="card_pol_base"):
        ui.card_title("개인 기준선과 z 점수 경계")
        st.markdown(
            "- 분석 단위는 로그인 활동이 있는 **사용자×날짜**, 개인 기준선은 **당일을 제외한 직전 30활동일**\n"
            "- 점수 대상: 과거 활동일 10일 이상 + 첫 활동 후 30일 이상. 미충족 날짜는 **기준선 부족**(점수 미산출, 정상 0점과 구분)\n"
            "- z = (당일 값 − 개인 평균) ÷ max(개인 표준편차, 1)\n"
            "- 보정기간(2010-01~05) z 분포의 99 / 99.75 / 99.95 백분위 이상이면 1 / 2 / 3점\n"
            "- 두 채널은 합산하지 않고 따로 표시합니다. **조사 대상 = 이메일 주의 이상 또는 로그온 주의 이상**")
        th = pd.DataFrame([{"채널": ui.FEATURE_CHANNEL[k], "지표": sv.FEATURES[k], "1점 z 경계": v[0], "2점 z 경계": v[1],
                            "3점 z 경계": v[2]} for k, v in meta["thresholds"].items()])
        st.dataframe(th, hide_index=True, width="stretch", column_config={
            k: st.column_config.NumberColumn(format="%.4f") for k in ["1점 z 경계", "2점 z 경계", "3점 z 경계"]})
    with st.container(border=True, key="card_pol_src"):
        ui.card_title("데이터 출처")
        st.markdown(
            f"- 모델 버전 `{prov['model']}` · 점수 데이터 `{prov['source']}` (SHA-256 `{prov['sha256'][:16]}…`)\n"
            f"- {meta['start']} ~ {meta['end']} · {meta['users']:,}명 · {meta['rows']:,} 사용자·일 "
            f"(점수 대상 {meta['scored_rows']:,} · 기준선 부족 {meta['warmup_rows']:,})\n"
            "- 로딩 시 저장된 점수·등급·조사 대상을 확정 정책으로 다시 계산해 일치 여부를 검사합니다. "
            "정답(내부자) 자료는 이 화면에 연결하지 않습니다.\n"
            "- 점수는 평소와 다른 행동의 크기를 나타내는 **조사 우선순위**이며, 위협 행동 확정·차단 판단이 아닙니다.")
