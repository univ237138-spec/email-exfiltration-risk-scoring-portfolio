"""이메일 외부유출 위험 분석 (보안담당자용 대시보드).

실행: cd dashboard && streamlit run app.py  (기본 포트 8503)
확정 산출물(dashboard/data)을 읽기 전용으로 사용한다.
"""
from datetime import timedelta
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

import services as sv
import ui
from views import detail, overview, policy, ranking

HERE = Path(__file__).resolve().parent
st.set_page_config(page_title="SIEM봤다 · 이메일 외부유출 위험 분석", page_icon=":material/shield_person:",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown(f"<style>{(HERE / 'styles' / 'app.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

try:
    data, meta, provenance = ui.snapshot(sv.signature())
except (FileNotFoundError, ValueError) as exc:
    st.error(f"확정 데이터를 불러올 수 없습니다: {exc}")
    st.stop()

FIRST, LAST = data.date.min().date(), data.date.max().date()
PRESETS = {"최근 7일": 7, "최근 30일": 30, "최근 90일": 90, "전체 기간": None, "직접 선택": "custom"}
ss = st.session_state
# Keep filter widget values when a page that hides them is visited.
for key in ("f_preset", "f_range", "f_dept", "f_role", "f_query"):
    if key in ss:
        ss[key] = ss[key]
ss.setdefault("f_preset", "최근 30일")
ss.setdefault("f_range", (LAST - timedelta(days=29), LAST))
ss.setdefault("f_dept", "전체")
ss.setdefault("f_role", "전체")
ss.setdefault("f_query", "")


def _apply_preset():
    days = PRESETS[ss.f_preset]
    if days is None:
        ss.f_range = (FIRST, LAST)
    elif days != "custom":
        ss.f_range = (max(FIRST, LAST - timedelta(days=days - 1)), LAST)


def _custom_range():
    ss.f_preset = "직접 선택"


pages = {
    "overview": st.Page(overview.render, title="대시보드", icon=":material/space_dashboard:",
                        url_path="overview", default=True),
    "ranking": st.Page(ranking.render, title="위험도 랭킹", icon=":material/military_tech:", url_path="ranking"),
    "detail": st.Page(detail.render, title="사용자 분석", icon=":material/person_search:", url_path="user"),
    "policy": st.Page(policy.render, title="점수·등급 기준", icon=":material/rule:", url_path="policy"),
}
ui.PAGES.update(pages)
page = st.navigation(list(pages.values()), position="sidebar")

st.logo(str(HERE / "assets" / "siem-bwatda-dark.png"), size="large")
with st.sidebar:
    st.markdown(
        f"""<div class="side-info">
        <div class="side-label">분석 모델</div><div class="side-value">{escape(provenance['model'])}</div>
        <div class="side-label">데이터 기간</div><div class="side-value">{FIRST} ~ {LAST}</div>
        <div class="side-label">분석 규모</div><div class="side-value">{meta['users']:,}명 · {meta['rows']:,} 사용자·일</div>
        <div class="side-foot">점수는 조사 우선순위를 돕는 지표이며, 최종 판단은 보안담당자가 합니다.</div>
        </div>""", unsafe_allow_html=True)

SUBTITLES = {
    "대시보드": "선택 기간의 이메일·로그온 경보와 먼저 확인할 사용자를 한눈에 확인하세요.",
    "위험도 랭킹": "조사 대상(이메일 또는 로그온 주의 이상)을 사용자별·사용자·일별로 정렬해 확인합니다.",
    "사용자 분석": "8개 지표의 평소 대비 변화와 점수 구성, 반복 여부를 확인해 추가 조사 여부를 판단합니다.",
    "점수·등급 기준": "확정 모델 email-review-v2.2의 점수 산출·등급·조사 대상 기준입니다.",
}

show_filters = page.title != "점수·등급 기준"
head, *controls = st.columns([2.0, 0.85, 1.3, 1.05, 0.8], vertical_alignment="bottom") if show_filters \
    else st.columns([1])
with head:
    st.markdown(f'<div class="page-title">{escape(page.title)}</div>'
                f'<div class="page-sub">{escape(SUBTITLES[page.title])}</div>', unsafe_allow_html=True)

if show_filters:
    departments = ["전체"] + sorted(data.department.unique())
    roles = ["전체"] + sorted(data.role.unique())
    if ss.f_dept not in departments:
        ss.f_dept = "전체"
    if ss.f_role not in roles:
        ss.f_role = "전체"
    controls[0].selectbox("기간", list(PRESETS), key="f_preset", on_change=_apply_preset)
    controls[1].date_input("조회 기간", key="f_range", min_value=FIRST, max_value=LAST, on_change=_custom_range,
                           format="YYYY-MM-DD")
    controls[2].selectbox("부서", departments, key="f_dept")
    with controls[3].popover("필터", icon=":material/tune:", use_container_width=True):
        st.selectbox("직무", roles, key="f_role")
        st.text_input("사용자 ID·이름 검색", key="f_query", placeholder="예: XHW0498")
        if st.button("필터 초기화", use_container_width=True):
            for key in ("f_preset", "f_range", "f_dept", "f_role", "f_query"):
                ss.pop(key, None)
            st.rerun()

rng = ss.f_range if isinstance(ss.f_range, (tuple, list)) else (ss.f_range,)
start = pd.Timestamp(rng[0])
end = pd.Timestamp(rng[1] if len(rng) > 1 else rng[0])
scope = sv.filter_scope(data, start, end, ss.f_dept, ss.f_role, ss.f_query)
prev_start, prev_end = sv.previous_window(start, end)
prev = None
if prev_end.date() >= FIRST:
    prev = sv.filter_scope(data, max(prev_start, pd.Timestamp(FIRST)), prev_end, ss.f_dept, ss.f_role, ss.f_query)
ss["_ctx"] = ui.Context(data, meta, provenance, start, end, ss.f_dept, ss.f_role, ss.f_query, scope, prev,
                        (prev_start, prev_end) if prev is not None else None)

page.run()
