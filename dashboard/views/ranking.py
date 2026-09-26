"""위험도 랭킹: 사용자별 랭킹과 사용자·일 조사 목록 (전체 접근·CSV)."""
import pandas as pd
import streamlit as st

import services as sv
import ui

PAGE_SIZE = 50


def _open_button(frame, rows, key):
    disabled = not rows
    label = "선택한 사용자 상세 분석" if rows else "표에서 행을 선택하면 상세 분석으로 이동할 수 있습니다"
    if st.button(label, icon=":material/arrow_forward:", disabled=disabled, type="primary", key=key):
        r = frame.iloc[rows[0]]
        ui.open_detail(r.user, r.date)


def _users(c):
    ranking = sv.user_ranking(c.scope)
    ui.card_title("사용자별 위험도 랭킹", f"조사 대상 사용자 {len(ranking):,}명 · 가장 강한 경보일 기준 정렬")
    if ranking.empty:
        ui.empty_state("선택 조건에 조사 대상 경보가 없습니다.")
        return
    grade = [r.risk_grade if sv.RANK[r.risk_grade] >= sv.RANK[r.logon_grade] else r.logon_grade
             for r in ranking.itertuples()]
    table = pd.DataFrame({
        "순위": range(1, len(ranking) + 1), "사용자 ID": ranking.user, "이름": ranking.employee_name,
        "부서": ranking.department, "직무": ranking.role, "최고 등급": grade,
        "이메일": ranking.total_score.astype(int), "로그온": ranking.logon_score.astype(int),
        "경보일 수": ranking.alert_days.astype(int), "대표 경보일": ranking.date.dt.strftime("%Y-%m-%d"),
        "첫 경보일": ranking.first_alert.dt.strftime("%Y-%m-%d"), "최근 경보일": ranking.last_alert.dt.strftime("%Y-%m-%d"),
        "주요 근거": [sv.reason(r) for _, r in ranking.iterrows()],
    })
    styled = table.style.map(lambda v: f"color:{ui.GRADE_TEXT.get(v, ui.INK)};font-weight:700", subset=["최고 등급"])
    event = st.dataframe(styled, hide_index=True, width="stretch", height=560, on_select="rerun",
                         selection_mode="single-row", key=f"rank_users_{c.key}", column_config={
                             "이메일": st.column_config.ProgressColumn("이메일 점수", min_value=0,
                                                                    max_value=max(6, int(table["이메일"].max())), format="%d점"),
                             "로그온": st.column_config.ProgressColumn("로그온 점수", min_value=0, max_value=3, format="%d점"),
                             "경보일 수": st.column_config.NumberColumn(format="%d일"),
                             "주요 근거": st.column_config.TextColumn(width="large")})
    a, b = st.columns([3, 1])
    with a:
        _open_button(ranking, event.selection.rows, "open_user_rank")
    b.download_button("사용자 랭킹 CSV", sv.csv_bytes(table), f"user_ranking_{c.start:%Y%m%d}_{c.end:%Y%m%d}.csv",
                      "text/csv", icon=":material/download:", width="stretch")


def _queue(c):
    all_alerts = c.scope[c.scope.review_target]
    f1, f2, f3 = st.columns(3)
    channel = f1.selectbox("경보 채널", ["전체", "이메일", "로그온", "둘 다"], key="q_channel")
    grade = f2.selectbox("최고 등급", ["전체", "위험", "주의"], key="q_grade")
    order = f3.selectbox("정렬", ["우선순위", "최근 날짜", "이메일 점수", "로그온 점수", "반복 경보"], key="q_order")
    queue = sv.review_queue(c.scope, channel, grade, order)
    ui.card_title("조사 목록 (사용자·일)",
                  f"전체 조사 대상 {len(all_alerts):,} 사용자·일 중 {len(queue):,} 표시 · 목록 필터는 이 표에만 적용")
    if queue.empty:
        ui.empty_state("선택 조건에 해당하는 경보가 없습니다.")
        return
    pages = max(1, -(-len(queue) // PAGE_SIZE))
    page = st.number_input(f"페이지 (1~{pages})", 1, pages, 1, key=f"q_page_{c.key}{channel}{grade}{order}") \
        if pages > 1 else 1
    part = queue.iloc[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    table = sv.queue_table(part)
    event = st.dataframe(table, hide_index=True, width="stretch", height=min(35 * len(table) + 38, 600),
                         on_select="rerun", selection_mode="single-row",
                         key=f"queue_{c.key}{channel}{grade}{order}{page}",
                         column_config={"경보일 수": st.column_config.NumberColumn(format="%d일"),
                                        "주요 근거": st.column_config.TextColumn(width="large")})
    a, b = st.columns([3, 1])
    with a:
        _open_button(part, event.selection.rows, "open_user_queue")
    b.download_button("현재 목록 전체 CSV", sv.csv_bytes(sv.queue_table(queue)),
                      f"review_queue_{c.start:%Y%m%d}_{c.end:%Y%m%d}.csv", "text/csv",
                      icon=":material/download:", width="stretch")


def render():
    c = ui.ctx()
    if c.scope.empty:
        ui.empty_state()
        return
    t1, t2 = st.tabs(["사용자별 랭킹", "조사 목록 (사용자·일)"])
    with t1, st.container(border=True, key="card_rank_users"):
        _users(c)
    with t2, st.container(border=True, key="card_rank_queue"):
        _queue(c)
