"""사용자 분석: 8개 지표 근거, 채널별 점수 구성, 날짜별 변화, 연결 메일 후보, 조사 근거 내보내기."""
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import services as sv
import ui


@st.cache_data(show_spinner=False)
def _users(_data, signature):
    names = _data.drop_duplicates("user", keep="last").set_index("user").employee_name
    return names.sort_index()


def _sync_user():
    st.session_state.sel_user = st.session_state.d_user
    st.session_state.pop("sel_date", None)


def _sync_date():
    st.session_state.sel_date = pd.Timestamp(st.session_state.d_date)


def _jump():
    value = st.session_state.get("d_jump")
    if value:
        st.session_state.sel_date = pd.Timestamp(value)
    st.session_state.d_jump = None


def _controls(c):
    ss = st.session_state
    names = _users(c.data, sv.signature())
    if ss.get("sel_user") not in names.index:
        ranking = sv.user_ranking(c.scope)
        ss.sel_user = ranking.user.iloc[0] if len(ranking) else names.index[0]
    if ss.get("d_user") != ss.sel_user:
        ss.d_user = ss.sel_user
    a, b, d = st.columns([1.4, 1, 2.2], vertical_alignment="bottom")
    a.selectbox("사용자 (경보가 없는 사용자도 검색 가능)", list(names.index), key="d_user", on_change=_sync_user,
                format_func=lambda u: f"{u} · {names[u]}")
    history = c.data[c.data.user.eq(ss.sel_user)]
    in_period = history[history.date.between(c.start, c.end)]
    if in_period.empty:
        st.info(f"조회 기간({c.start:%Y-%m-%d}~{c.end:%Y-%m-%d})에 이 사용자의 활동 기록이 없어 전체 이력을 표시합니다.")
        in_period = history
    dates = list(in_period.date.sort_values(ascending=False))
    alerts = in_period[in_period.review_target]
    if ss.get("sel_date") not in dates:
        ss.sel_date = alerts.date.max() if len(alerts) else dates[0]
    if ss.get("d_date") != ss.sel_date:
        ss.d_date = ss.sel_date
    flag = dict(zip(in_period.date, in_period._priority))
    marks = {3: " · 위험", 2: " · 주의", 1: " · 관심", -1: " · 기준선 부족"}
    b.selectbox("날짜", dates, key="d_date", on_change=_sync_date,
                format_func=lambda x: f"{x:%Y-%m-%d}{marks.get(flag.get(x), '')}")
    if len(alerts):
        d.pills(f"기간 내 경보일 {alerts.date.nunique()}일 · 선택하면 이동", list(alerts.date.dt.strftime("%Y-%m-%d")),
                key="d_jump", on_change=_jump)
    else:
        d.caption("조회 기간에 이 사용자의 조사 대상 경보가 없습니다.")
    row = in_period[in_period.date.eq(ss.sel_date)].iloc[0]
    return row, in_period, alerts


def _header(row, alerts):
    top = row.risk_grade if sv.RANK[row.risk_grade] >= sv.RANK[row.logon_grade] else row.logon_grade
    base = "—" if pd.isna(row.base_n) else f"{int(row.base_n)}활동일"
    left, right = st.columns([1.1, 1.6], gap="medium")
    with left, st.container(border=True, key="card_profile"):
        st.markdown(
            f'<div class="sel-head"><span class="uid">{escape(row.user)}</span>{ui.badge(top)}'
            f'{ui.badge("조사 대상" if row.review_target else "조사 대상 아님", "")}</div>'
            f'<div class="sel-meta">{escape(row.employee_name)}</div>'
            f'<div class="comp"><div class="line"><span class="muted">부서</span><span>{escape(row.department)}</span></div>'
            f'<div class="line"><span class="muted">직무</span><span>{escape(row.role)}</span></div>'
            f'<div class="line"><span class="muted">선택일</span><span>{row.date:%Y-%m-%d} ({"월화수목금토일"[row.date.weekday()]})</span></div>'
            f'<div class="line"><span class="muted">개인 기준선</span><span>당일 제외 직전 {base}</span></div>'
            f'<div class="line"><span class="muted">기간 내 경보</span><span>{alerts.date.nunique()}일'
            + (f' · 첫 {alerts.date.min():%Y-%m-%d} · 최근 {alerts.date.max():%Y-%m-%d}' if len(alerts) else "")
            + "</span></div></div>", unsafe_allow_html=True)
    with right, st.container(border=True, key="card_scores"):
        st.markdown(
            f'<div class="score-row">'
            f'{ui.score_block("이메일", row.total_score, row.risk_grade, "0~1 정상 · 2 관심 · 3~4 주의 · 5+ 위험")}'
            f'{ui.score_block("로그온", row.logon_score, row.logon_grade, "0 정상 · 1 관심 · 2 관심/주의(z 조건) · 3 위험")}'
            f'</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="reason" style="margin-top:10px">{escape(sv.reason_sentence(row))}</div>',
                    unsafe_allow_html=True)


def _evidence(row, meta):
    ui.card_title("8개 지표 근거", "선택일 값 · 개인 평균(직전 30활동일) · z · 개별 점수")
    if not row.is_scored:
        past = int(row.active_day_seq) - 1
        st.warning(f"기준선 준비 중: 과거 활동일 {past}일(필요 10일 이상), 첫 활동 후 {int(row.days_since_first)}일"
                   "(필요 30일 이상). 점수와 등급을 판정하지 않으며 정상 0점과 다릅니다.")
    table = sv.evidence_table(row, meta)
    hit = table["점수"].fillna(0).gt(0)
    view = table.copy()
    blank = "해당 없음" if row.is_scored else "—"
    view["현재값"] = table["현재값"].map(lambda v: f"{v:g}")
    for col in ["평소 평균", "z", "표준편차"]:
        view[col] = table[col].map(lambda v: blank if v is None or pd.isna(v) else f"{v:.2f}")
    view["점수"] = table["점수"].map(lambda v: "—" if v is None or pd.isna(v) else f"+{int(v)}" if v else "0")
    styled = view.style.apply(lambda r: ["background-color:#3A1F24" if hit[r.name] else "" for _ in r], axis=1)
    st.dataframe(styled, hide_index=True, width="stretch", height=35 * 8 + 38,
                 column_order=["채널", "지표", "현재값", "평소 평균", "z", "점수", "적용 근거"],
                 column_config={"적용 근거": st.column_config.TextColumn(width="large")})
    with st.expander("표준편차와 정밀 z 경계 보기"):
        st.dataframe(view[["지표", "표준편차", "z 경계 (1 / 2 / 3점)"]], hide_index=True, width="stretch")
        st.caption("z = (선택일 값 − 개인 평균) ÷ max(개인 표준편차, 1). 경계는 보정기간(2010-01~05) 분포의 "
                   "99 / 99.75 / 99.95 백분위. 규칙형 2개는 z·평균을 쓰지 않습니다. 야간은 19시 이상 또는 07시 미만.")


def _composition(row):
    ui.card_title("채널별 점수 구성")
    if not row.is_scored:
        ui.empty_state("기준선 부족 · 점수 미산출")
        return
    lines = "".join(
        f'<div class="line"><span>{sv.FEATURES[c]}</span><span>{int(row[c + "_points"])}점</span></div>'
        for c in list(sv.EMAIL) + list(sv.RULES))
    discount = int(row.overlap_discount)
    email = (f'<h4>이메일</h4>{lines}'
             f'<div class="line"><span class="muted">중복 조정 (외부 발송·외부 첨부 중 작은 점수 제외)</span>'
             f'<span>−{discount}점</span></div>'
             f'<div class="line total"><span>이메일 점수</span><span>{int(row.total_score)}점 · {row.risk_grade}</span></div>')
    pc, night = int(row.other_pc_logon_cnt_points), int(row.night_logon_cnt_points)
    maxz = max(row.other_pc_logon_cnt_z, row.night_logon_cnt_z)
    note = ""
    if int(row.logon_score) == 2:
        note = (f'<div class="line"><span class="muted">2점 판정: 최대 z {maxz:.2f} '
                f'{"≥" if maxz >= 1.9443 else "<"} 1.9443</span><span>{row.logon_grade}</span></div>')
    logon = (f'<h4>로그온</h4><div class="line"><span>다른 PC 로그온</span><span>{pc}점</span></div>'
             f'<div class="line"><span>야간 로그온</span><span>{night}점</span></div>{note}'
             f'<div class="line total"><span>로그온 점수 = max({pc}, {night})</span>'
             f'<span>{int(row.logon_score)}점 · {row.logon_grade}</span></div>')
    st.markdown(f'<div class="comp">{email}{logon}</div>', unsafe_allow_html=True)
    st.caption("두 채널은 합산하지 않습니다. 조사 대상 = 이메일 주의 이상 또는 로그온 주의 이상.")


def _trend(row, history):
    ui.card_title("날짜별 점수 변화", "위: 이메일 · 아래: 로그온 · 막대 색 = 등급 · 기준선 부족일은 비어 있음")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, row_heights=[0.55, 0.45])
    shown = set()
    for r, (score, grade_col) in enumerate((("total_score", "risk_grade"), ("logon_score", "logon_grade")), start=1):
        for grade in ["정상", "관심", "주의", "위험"]:
            part = history[history[grade_col].eq(grade)]
            if part.empty:
                continue
            fig.add_trace(go.Bar(x=part.date, y=part[score].astype(float).clip(lower=0.08), name=grade,
                                 legendgroup=grade, showlegend=grade not in shown,
                                 marker=dict(color=ui.GRADE[grade], cornerradius=3), customdata=part[score],
                                 hovertemplate="%{x|%Y-%m-%d} · %{customdata}점 · " + grade + "<extra></extra>"),
                          row=r, col=1)
            shown.add(grade)
    for r in (1, 2):
        fig.add_vline(x=row.date, line=dict(color=ui.ACCENT, width=1.5, dash="dot"), row=r, col=1)
    fig.add_hline(y=3, line=dict(color=ui.GRADE["주의"], dash="dot", width=1), row=1, col=1)
    ui.style(fig, 330)
    fig.update_layout(barmode="overlay", bargap=0.35)
    fig.update_yaxes(title=dict(text="이메일", font=dict(size=11)), row=1, col=1, rangemode="tozero")
    fig.update_yaxes(title=dict(text="로그온", font=dict(size=11)), range=[0, 3.3], dtick=1, row=2, col=1)
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG, key="detail_trend")


def _indicator(row, history, meta):
    ui.card_title("지표별 실제값과 개인 기준선", "선택일 기준선은 조회 기간과 무관하게 전체 이력으로 계산된 값")
    feat = st.selectbox("지표", list(sv.FEATURES), format_func=lambda k: f"{sv.FEATURES[k]} ({ui.FEATURE_CHANNEL[k]})",
                        key="d_feat", label_visibility="collapsed")
    fig = go.Figure()
    if feat in sv.RULES:
        cnt = history[feat + "_cnt"]
        hit = history[feat + "_points"].fillna(0).gt(0)
        fig.add_trace(go.Bar(x=history.date, y=cnt, name=f"{sv.FEATURES[feat]} 건수", marker_color="#3987E5",
                             hovertemplate="%{x|%Y-%m-%d} · %{y}건<extra></extra>"))
        if hit.any():
            fig.add_trace(go.Scatter(x=history.date[hit], y=cnt[hit], mode="markers", name="점수 발생일",
                                     marker=dict(size=11, color=ui.GRADE["주의"], symbol="diamond",
                                                 line=dict(color=ui.SURFACE, width=2)),
                                     hovertemplate="%{x|%Y-%m-%d} · 점수 발생<extra></extra>"))
    else:
        t = meta["thresholds"][feat]
        scale = history[feat + "_sd"].clip(lower=1)
        series = [(history[feat], "선택일 값", "#3987E5", "solid", "lines+markers"),
                  (history[feat + "_mu"], "개인 평균", "#9AA8BC", "dash", "lines"),
                  (history[feat + "_mu"] + t[0] * scale, "1점 경계", ui.GRADE["관심"], "dot", "lines"),
                  (history[feat + "_mu"] + t[2] * scale, "3점 경계", ui.GRADE["위험"], "dot", "lines")]
        for y, name, color, dash, mode in series:
            fig.add_trace(go.Scatter(x=history.date, y=y, name=name, mode=mode,
                                     line=dict(color=color, width=2, dash=dash), marker=dict(size=5),
                                     hovertemplate="%{x|%Y-%m-%d} · %{y:.2f}<extra>" + name + "</extra>"))
    fig.add_vline(x=row.date, line=dict(color=ui.ACCENT, width=1.5, dash="dot"))
    ui.style(fig, 280)
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(title=dict(text=sv.UNITS[feat], font=dict(size=11)), rangemode="tozero")
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG, key="detail_feat")


def _links_and_export(c, row, history, alerts):
    links = sv.load_links(row)
    ui.card_title("추가 확인 근거와 내보내기")
    if links is None:
        st.caption("연결 메일 자료(link_events.parquet)가 없어 추가 근거를 확인할 수 없습니다.")
    elif links.empty:
        st.caption("선택일 전후 1일에 연결 메일 후보가 없습니다.")
    else:
        with st.expander(f"연결 메일 후보 {len(links)}건 (선택일 ±1일)", expanded=True):
            st.dataframe(links.rename(columns={
                "logon_time": "로그온 시각", "pc": "PC", "pc_owner": "PC 소유자", "mail_time": "메일 시각",
                "mail_user": "발송 계정", "n_rcpt": "수신자 수"}).drop(columns=["user", "day"]),
                hide_index=True, width="stretch")
            st.caption("다른 사용자 PC에 로그온한 뒤 60분 안에 같은 PC에서 그 PC 소유자 계정으로 메일이 발송된 시간상 연결 "
                       "후보입니다. 점수·조사 대상에는 반영하지 않으며 실제 유출을 입증하는 자료가 아닙니다.")
    bundle = sv.investigation_zip(row, history, c.meta, c.provenance, c.filters, links)
    st.download_button("조사 근거 내보내기 (ZIP: 지표 근거·경보 이력·출처)", bundle,
                       f"evidence_{row.user}_{row.date:%Y%m%d}.zip", "application/zip",
                       icon=":material/download:", width="stretch", type="primary")


def render():
    c = ui.ctx()
    row, history, alerts = _controls(c)
    _header(row, alerts)
    left, right = st.columns([1.65, 1], gap="medium")
    with left, st.container(border=True, key="card_evidence"):
        _evidence(row, c.meta)
    with right, st.container(border=True, key="card_comp"):
        _composition(row)
    left, right = st.columns([1, 1], gap="medium")
    with left, st.container(border=True, key="card_dtrend"):
        _trend(row, history)
    with right, st.container(border=True, key="card_feat"):
        _indicator(row, history, c.meta)
    with st.container(border=True, key="card_links"):
        _links_and_export(c, row, history, alerts)
