"""대시보드: KPI → TOP 10 + 선택 사용자 → 분포 3종 → 일별 경보 추이."""
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import services as sv
import ui


def _kpis(c):
    s = sv.summary(c.scope)
    p = sv.summary(c.prev) if c.prev is not None else None
    days = (c.end - c.start).days + 1
    compare = f"직전 {days}일"
    d = (lambda k: s[k] - p[k]) if p else (lambda k: None)
    cards = [
        ui.kpi("users", "#3987E5", "분석 사용자", f"{s['users']:,}<small>명</small>", d("users"), None, compare),
        ui.kpi("target", "#EC835A", "조사 대상 사용자", f"{s['review_users']:,}<small>명</small>",
               d("review_users"), True, compare),
        ui.kpi("calendar", "#FAB219", "경보 사용자·일", f"{s['alerts']:,}<small>건</small>", d("alerts"), True, compare),
        ui.kpi("shield", "#D03B3B", "위험 경보 사용자·일", f"{s['danger']:,}<small>건</small>", d("danger"), True, compare),
    ]
    for col, html in zip(st.columns(4), cards):
        col.markdown(html, unsafe_allow_html=True)
    st.markdown(f'<div class="scope-line"><span><b>{c.start:%Y-%m-%d} ~ {c.end:%Y-%m-%d}</b></span>'
                f'<span>점수 대상 <b>{s["scored"]:,}</b> 사용자·일</span>'
                f'<span>기준선 부족(점수 미산출) <b>{s["warmup"]:,}</b> 사용자·일</span>'
                '<span class="rule">조사 대상 = 이메일 주의 이상 또는 로그온 주의 이상</span></div>',
                unsafe_allow_html=True)


def _top10(c, ranking):
    ui.card_title("조사 우선순위 TOP 10 (사용자)", "사용자별 가장 강한 경보일 기준 · 행을 선택하면 오른쪽에 근거 표시")
    if ranking.empty:
        ui.empty_state("선택 기간에 조사 대상 경보가 없습니다.")
        return None
    top = ranking.head(10)
    grade = [r.risk_grade if sv.RANK[r.risk_grade] >= sv.RANK[r.logon_grade] else r.logon_grade
             for r in top.itertuples()]
    table = pd.DataFrame({
        "순위": range(1, len(top) + 1), "사용자": top.user.values,
        "이메일": top.total_score.astype(int).values, "로그온": top.logon_score.astype(int).values,
        "등급": grade, "경보일": top.alert_days.astype(int).values,
        "주요 근거": [sv.reason(r) for _, r in top.iterrows()],
    })
    email_max = max(6, int(table["이메일"].max()))
    styled = table.style.map(lambda v: f"color:{ui.GRADE_TEXT.get(v, ui.INK)};font-weight:700", subset=["등급"])
    event = st.dataframe(
        styled, hide_index=True, width="stretch", height=35 * len(table) + 38, key=f"top10_{c.key}",
        on_select="rerun", selection_mode="single-row",
        column_config={
            "순위": st.column_config.NumberColumn(width=40),
            "사용자": st.column_config.TextColumn(width=78),
            "이메일": st.column_config.ProgressColumn("이메일 점수", min_value=0, max_value=email_max, format="%d점",
                                                   width=96, help="0~1 정상 · 2 관심 · 3~4 주의 · 5+ 위험"),
            "로그온": st.column_config.ProgressColumn("로그온 점수", min_value=0, max_value=3, format="%d점",
                                                   width=96, help="0 정상 · 3 위험 · 2점+z 조건 주의"),
            "등급": st.column_config.TextColumn("최고 등급", width=62),
            "경보일": st.column_config.NumberColumn("경보일", format="%d일", width=54),
            "주요 근거": st.column_config.TextColumn(width="large"),
        })
    st.page_link(ui.PAGES["ranking"], label="전체 랭킹 보기", icon=":material/arrow_forward:")
    rows = event.selection.rows
    if rows:
        chosen = top.iloc[rows[0]]
        ui.select(chosen.user, chosen.date)
        return chosen
    return None


def _selected(c, ranking, chosen):
    ss = st.session_state
    if chosen is None:
        match = ranking[ranking.user.eq(ss.get("sel_user"))]
        chosen = match.iloc[0] if len(match) else ranking.iloc[0]
    user_alerts = c.scope[c.scope.user.eq(chosen.user) & c.scope.review_target]
    row = chosen
    top_grade = row.risk_grade if sv.RANK[row.risk_grade] >= sv.RANK[row.logon_grade] else row.logon_grade
    st.markdown(
        f'<div class="sel-head">선택된 사용자: <span class="uid">{escape(row.user)}</span>{ui.badge(top_grade)}</div>'
        f'<div class="sel-meta">{escape(row.employee_name)} · {escape(row.department)} · {escape(row.role)}</div>'
        f'<div class="score-row">'
        f'{ui.score_block("이메일", row.total_score, row.risk_grade, "0~1 정상 · 2 관심 · 3~4 주의 · 5+ 위험")}'
        f'{ui.score_block("로그온", row.logon_score, row.logon_grade, "두 로그온 지표 중 큰 점수 (0~3)")}</div>'
        f'<div class="period"><span>대표 경보일 <b>{row.date:%Y-%m-%d}</b></span>'
        f'<span>기간 내 경보 <b>{user_alerts.date.nunique()}일</b></span>'
        f'<span>첫 경보 <b>{user_alerts.date.min():%m-%d}</b> · 최근 <b>{user_alerts.date.max():%m-%d}</b></span></div>',
        unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["위험 근거", "점수 추이", "경보 이력"])
    with t1:
        st.markdown(ui.evidence_items(row), unsafe_allow_html=True)
    with t2:
        hist = c.scope[c.scope.user.eq(row.user)]
        fig = go.Figure()
        for col, name, color in (("total_score", "이메일 점수", ui.CHANNEL["이메일만"]),
                                 ("logon_score", "로그온 점수", ui.CHANNEL["로그온만"])):
            fig.add_trace(go.Scatter(x=hist.date, y=hist[col].astype(float), name=name, mode="lines+markers",
                                     line=dict(color=color, width=2), marker=dict(size=5),
                                     hovertemplate="%{x|%Y-%m-%d} · %{y:.0f}점<extra>" + name + "</extra>"))
        fig.add_hline(y=3, line=dict(color=ui.GRADE["주의"], dash="dot", width=1),
                      annotation_text="이메일 주의 3점", annotation_font_color=ui.INK2)
        ui.style(fig, 230)
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG, key="sel_trend")
    with t3:
        hist_tbl = user_alerts.sort_values("date", ascending=False)
        st.dataframe(pd.DataFrame({
            "날짜": hist_tbl.date.dt.strftime("%Y-%m-%d"),
            "이메일": hist_tbl.total_score.astype(int).astype(str) + "점 · " + hist_tbl.risk_grade,
            "로그온": hist_tbl.logon_score.astype(int).astype(str) + "점 · " + hist_tbl.logon_grade,
            "채널": hist_tbl.alert_channel}), hide_index=True, width="stretch", height=min(35 * len(hist_tbl) + 38, 230))
    if st.button("사용자 상세 분석", icon=":material/arrow_forward:", width="stretch", type="primary"):
        ui.open_detail(row.user, row.date)


def _distribution(c):
    ui.card_title("위험 수준 분포 (사용자)", "기간 내 최고 채널 등급")
    counts = sv.user_grade_distribution(c.scope)
    total = sum(counts[g] for g in sv.GRADE_ORDER)
    left, right = st.columns([1.05, 1], vertical_alignment="center")
    left.plotly_chart(ui.donut(counts), width="stretch", config=ui.PLOT_CONFIG, key="donut")
    rules = {"위험": "이메일 5점+ 또는 로그온 3점", "주의": "이메일 3~4점 또는 로그온 주의",
             "관심": "이메일 2점 또는 로그온 관심", "정상": "이메일 0~1점 · 로그온 0점"}
    legend = "".join(
        f'<div class="legend-row"><div class="sw" style="background:{ui.GRADE[g]}"></div><div>'
        f'<b>{g}</b> {counts[g]:,}명 <span class="sub">({counts[g] / total * 100 if total else 0:.1f}%)</span>'
        f'<br><span class="sub">{rules[g]}</span></div></div>'
        for g in sv.GRADE_ORDER)
    if counts["기준선 부족"]:
        legend += f'<div class="legend-row sub">기준선 부족만 있는 사용자 {counts["기준선 부족"]:,}명 별도</div>'
    right.markdown(legend, unsafe_allow_html=True)


def _score_hist(c):
    ui.card_title("일별 점수 분포 (사용자·일)", "세로축 로그 눈금")
    channel = st.segmented_control("채널", ["이메일", "로그온"], default="이메일", key="dist_channel",
                                   label_visibility="collapsed") or "이메일"
    col = "total_score" if channel == "이메일" else "logon_score"
    dist = sv.score_distribution(c.scope, col)
    if dist.empty:
        ui.empty_state()
        return
    if channel == "이메일":
        grade = ["정상" if s <= 1 else "관심" if s == 2 else "주의" if s <= 4 else "위험" for s in dist.index]
    else:
        grade = ["정상" if s == 0 else "위험" if s == 3 else "관심·주의" for s in dist.index]
    colors = [ui.GRADE.get(g, ui.GRADE["관심"]) for g in grade]
    fig = go.Figure(go.Bar(x=dist.index, y=dist.values, marker=dict(color=colors, cornerradius=4),
                           text=[f"{v:,}" for v in dist.values], textposition="outside",
                           textfont=dict(color=ui.INK2, size=11), customdata=grade,
                           hovertemplate="%{x}점 · %{customdata}<br>%{y:,} 사용자·일<extra></extra>"))
    ui.style(fig, 235, legend=False)
    fig.update_yaxes(type="log", title=None, showticklabels=False, showgrid=False)
    fig.update_xaxes(dtick=1, title=dict(text=f"{channel} 점수", font=dict(size=11)))
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG, key="score_hist")
    if channel == "로그온":
        st.caption("로그온 2점은 두 로그온 z의 최댓값이 1.9443 이상이면 주의, 아니면 관심")


def _anomalies(c):
    ui.card_title("지표별 점수 발생 현황", "점수가 붙은 사용자·일 · 직전 기간 대비")
    now = sv.indicator_counts(c.scope)
    before = sv.indicator_counts(c.prev) if c.prev is not None else None
    rows = [f'<div class="an-legend"><span><i style="background:{ui.CHANNEL["이메일만"]}"></i>이메일 지표</span>'
            f'<span><i style="background:{ui.CHANNEL["로그온만"]}"></i>로그온 지표</span>'
            '<span class="an-cols">건수 · 증감</span></div>']
    for feat, n in sorted(now.items(), key=lambda kv: -kv[1]):
        ch = ui.FEATURE_CHANNEL[feat]
        dot = ui.CHANNEL["이메일만" if ch == "이메일" else "로그온만"]
        if before is None:
            delta = '<span class="d flat">—</span>'
        else:
            diff = n - before[feat]
            cls, arrow = ("up", "▲") if diff > 0 else ("down", "▼") if diff < 0 else ("flat", "")
            delta = f'<span class="d {cls}">{arrow} {abs(diff):,}</span>' if diff else '<span class="d flat">0</span>'
        rows.append(f'<div class="an"><div class="ev-dot" style="background:{dot}"></div>'
                    f'<span class="name">{sv.FEATURES[feat]}</span>'
                    f'<span class="cnt">{n:,}</span>{delta}</div>')
    st.markdown("".join(rows), unsafe_allow_html=True)


def _trend(c):
    ui.card_title("일별 경보 추이", "조사 대상 사용자·일 · 채널 구성 (서로 겹치지 않음)")
    daily = sv.daily_counts(c.scope, c.start, c.end)
    fig = go.Figure()
    for name, color in ui.CHANNEL.items():
        fig.add_trace(go.Bar(x=daily.index, y=daily[name], name=name, marker=dict(color=color, line=dict(color=ui.SURFACE, width=1)),
                             hovertemplate="%{x|%Y-%m-%d} · %{y:.0f} 사용자·일<extra>" + name + "</extra>"))
    empty = daily["점수 대상"].eq(0)
    if empty.any():
        fig.add_trace(go.Scatter(x=daily.index[empty], y=[0] * int(empty.sum()), mode="markers", name="점수 대상 없음",
                                 marker=dict(symbol="line-ew-open", size=10, color=ui.MUTED, line=dict(width=2)),
                                 hovertemplate="%{x|%Y-%m-%d} · 관측·점수 대상 없음<extra></extra>"))
    ui.style(fig, 260)
    fig.update_layout(barmode="stack", hovermode="x unified", legend_traceorder="normal")
    fig.update_yaxes(title=dict(text="사용자·일", font=dict(size=11)), rangemode="tozero")
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG, key="trend")


def render():
    c = ui.ctx()
    if c.scope.empty:
        ui.empty_state()
        return
    _kpis(c)
    ranking = sv.user_ranking(c.scope)
    left, right = st.columns([1.7, 1], gap="medium")
    with left:
        with st.container(border=True, key="card_top10"):
            chosen = _top10(c, ranking)
    with right:
        with st.container(border=True, key="card_selected"):
            if ranking.empty:
                ui.card_title("선택된 사용자")
                ui.empty_state("조사 대상이 없어 표시할 사용자가 없습니다.")
            else:
                _selected(c, ranking, chosen)
    a, b, d = st.columns([1.15, 1, 1], gap="medium")
    with a, st.container(border=True, key="card_dist"):
        _distribution(c)
    with b, st.container(border=True, key="card_hist"):
        _score_hist(c)
    with d, st.container(border=True, key="card_anom"):
        _anomalies(c)
    with st.container(border=True, key="card_trend"):
        _trend(c)
