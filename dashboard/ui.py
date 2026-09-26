"""Shared state, theme tokens and HTML fragments for the risk dashboard."""
from dataclasses import dataclass
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import services as sv

PAGES = {}

# Status colors carry grade; always shown next to the grade word, never alone.
GRADE = {"정상": "#7D8BA1", "관심": "#FAB219", "주의": "#EC835A", "위험": "#D03B3B", "기준선 부족": "#4A5568"}
GRADE_TEXT = {"정상": "#B8C3D3", "관심": "#FFD166", "주의": "#F6A984", "위험": "#FF8C8C", "기준선 부족": "#9AA8BC"}
# Categorical channel identity (validated order: blue, orange, aqua).
CHANNEL = {"이메일만": "#3987E5", "로그온만": "#D95926", "둘 다": "#199E70"}
FEATURE_CHANNEL = {c: ("로그온" if c in sv.LOGON else "이메일") for c in sv.FEATURES}
INK, INK2, MUTED, GRID, SURFACE = "#E6EDF7", "#9AA8BC", "#6B7A90", "#1F2A3F", "#131C2E"
ACCENT = "#22B8E6"


@dataclass
class Context:
    data: pd.DataFrame
    meta: dict
    provenance: dict
    start: pd.Timestamp
    end: pd.Timestamp
    department: str
    role: str
    query: str
    scope: pd.DataFrame
    prev: pd.DataFrame | None
    prev_range: tuple | None

    @property
    def key(self):
        return f"{self.start:%Y%m%d}{self.end:%Y%m%d}{self.department}{self.role}{self.query}"

    @property
    def filters(self):
        return dict(start=str(self.start.date()), end=str(self.end.date()), department=self.department,
                    role=self.role, query=self.query)


def ctx() -> Context:
    return st.session_state["_ctx"]


@st.cache_resource(show_spinner="확정 점수 데이터를 불러오고 정책과 대조하는 중…")
def snapshot(signature):
    return sv.load_snapshot()


def select(user, date):
    st.session_state.sel_user = user
    st.session_state.sel_date = pd.Timestamp(date)


def open_detail(user, date):
    select(user, date)
    st.switch_page(PAGES["detail"])


# ---- HTML fragments -------------------------------------------------------
def fmt(n):
    return "—" if n is None or pd.isna(n) else f"{int(n):,}"


def badge(grade, prefix=""):
    color, text = GRADE.get(grade, MUTED), GRADE_TEXT.get(grade, INK2)
    return (f'<span class="badge" style="color:{text};background:{color}26;border:1px solid {color}66">'
            f"{escape(prefix)}{escape(str(grade))}</span>")


ICONS = {
    "users": '<path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7 0a3 3 0 1 0 0-6M2 21v-1a6 6 0 0 1 6-6h2a6 6 0 0 1 6 6v1m2-7a5 5 0 0 1 4 5v2"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4m8-4v4m-4 7v3m0 2.5v.01"/>',
    "shield": '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3Z"/><path d="M12 8v5m0 3v.01"/>',
}


def kpi(icon, color, label, value, delta=None, higher_is_worse=True, compare=""):
    delta_html = '<div class="kpi-delta muted">직전 기간 데이터 없음</div>'
    if delta is not None:
        if delta == 0:
            delta_html = f'<div class="kpi-delta muted">변화 없음 <span>(vs {compare})</span></div>'
        else:
            worse = (delta > 0) == higher_is_worse
            tone = "neutral" if higher_is_worse is None else ("bad" if worse else "good")
            arrow = "▲" if delta > 0 else "▼"
            delta_html = (f'<div class="kpi-delta {tone}">{arrow} {abs(delta):,} '
                          f'<span>(vs {compare})</span></div>')
    return (f'<div class="kpi"><div class="kpi-icon" style="color:{color};background:{color}1f">'
            f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS[icon]}</svg></div>'
            f'<div><div class="kpi-label">{escape(label)}</div><div class="kpi-value">{value}</div>'
            f"{delta_html}</div></div>")


def card_title(title, note=""):
    note_html = f'<span class="card-note">{escape(note)}</span>' if note else ""
    st.markdown(f'<div class="card-title">{escape(title)}{note_html}</div>', unsafe_allow_html=True)


def grade_steps(grade):
    """Four-step grade meter: shows position on the grade ladder without inventing a 0-100 scale."""
    rank = sv.RANK.get(grade, -1)
    cells = []
    for i, g in enumerate(["정상", "관심", "주의", "위험"]):
        on = i <= rank
        color = GRADE[grade] if on else "#243149"
        cells.append(f'<div class="step" style="background:{color}"></div>')
    labels = "".join(f"<span>{g}</span>" for g in ["정상", "관심", "주의", "위험"])
    return f'<div class="steps">{"".join(cells)}</div><div class="step-labels">{labels}</div>'


def score_block(channel, score, grade, rule):
    value = "—" if pd.isna(score) else f"{int(score)}<small>점</small>"
    return (f'<div class="score-block"><div class="score-head"><span>{channel} 점수</span>{badge(grade)}</div>'
            f'<div class="score-num" style="color:{GRADE_TEXT.get(grade, INK)}">{value}</div>'
            f"{grade_steps(grade)}<div class='score-rule'>{escape(rule)}</div></div>")


def evidence_items(row):
    """List of indicators that scored on the day, with their raw value against the personal baseline."""
    if not row.is_scored:
        return '<div class="empty">기준선 준비 중 · 점수 미산출</div>'
    items = []
    for c, label in sv.FEATURES.items():
        pts = row[c + "_points"]
        if not pts or pd.isna(pts) or pts <= 0:
            continue
        unit = sv.UNITS[c]
        if c == "jobkw_mail":
            detail = f"키워드 3개 이상 회사메일 {int(row.jobkw_mail_cnt)}{unit}"
        elif c == "night_mail":
            detail = f"야간 메일 {int(row.night_mail_cnt)}{unit} · 직전 30활동일 야간 메일 0일"
        else:
            detail = f"{row[c]:g}{unit} · 평소 {row[c + '_mu']:.2f} · z {row[c + '_z']:.2f}"
        ch = FEATURE_CHANNEL[c]
        dot = CHANNEL["이메일만" if ch == "이메일" else "로그온만"]
        items.append((int(pts), f'<div class="ev"><div class="ev-dot" style="background:{dot}"></div>'
                                f'<div class="ev-body"><div class="ev-title">{label}<span class="chip">{ch}</span></div>'
                                f'<div class="ev-detail">{escape(detail)}</div></div>'
                                f'<div class="ev-pts">+{int(pts)}</div></div>'))
    if not items:
        return '<div class="empty">점수가 발생한 지표가 없습니다.</div>'
    html = "".join(h for _, h in sorted(items, key=lambda x: -x[0]))
    if row.overlap_discount and row.overlap_discount > 0:
        html += (f'<div class="ev-note">외부 발송·외부 첨부는 큰 점수 한 번만 반영 '
                 f'(중복 −{int(row.overlap_discount)})</div>')
    return html


def empty_state(message="선택 조건에 해당하는 기록이 없습니다."):
    st.markdown(f'<div class="empty big">{escape(message)}</div>', unsafe_allow_html=True)


# ---- Plotly theme ---------------------------------------------------------
def style(fig, height, legend=True):
    fig.update_layout(
        height=height, margin=dict(l=4, r=8, t=8, b=4), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(color=INK2, size=12, family="Pretendard, 'Segoe UI', sans-serif"),
        showlegend=legend, legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=INK2),
                                       bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#1B263B", bordercolor="#33415C", font=dict(color=INK)),
        bargap=0.25)
    fig.update_xaxes(gridcolor=GRID, linecolor="#2A3752", tickcolor="#2A3752", zeroline=False, color=MUTED)
    fig.update_yaxes(gridcolor=GRID, linecolor="#2A3752", zeroline=False, color=MUTED)
    return fig


PLOT_CONFIG = {"displayModeBar": False}


def donut(counts):
    labels = [g for g in sv.GRADE_ORDER if counts.get(g)]
    fig = go.Figure(go.Pie(labels=labels, values=[counts[g] for g in labels], hole=0.7, sort=False,
                           direction="clockwise", marker=dict(colors=[GRADE[g] for g in labels],
                                                              line=dict(color=SURFACE, width=2)),
                           textinfo="none", hovertemplate="%{label}: %{value:,}명 (%{percent})<extra></extra>"))
    total = sum(counts[g] for g in sv.GRADE_ORDER)
    fig.add_annotation(text=f"<b style='font-size:22px;color:{INK}'>{total:,}</b><br>"
                            f"<span style='color:{INK2}'>사용자</span>", showarrow=False)
    return style(fig, 210, legend=False)
