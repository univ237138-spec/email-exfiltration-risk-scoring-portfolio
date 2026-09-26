"""발표용 샘플 데이터 7종 ERD (PNG + SVG).

실행: 프로젝트 루트에서 python outputs/figures/발표자료/make_data_erd.py
수치·관계 출처: docs/data/00_데이터_관계_개요.md, 원본 CSV 헤더·행 수 재확인(2026-09-24)
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent

INK = "#1f2933"
MUTED = "#6b7785"
USED_HEAD, USED_EDGE, USED_BODY = "#2a6fdb", "#2a6fdb", "#f5f9ff"
UNUSED_HEAD, UNUSED_EDGE, UNUSED_BODY = "#8d97a3", "#9aa3ad", "#fafbfc"
PK_C, FK_C, UK_C = "#b7791f", "#2a6fdb", "#7c5cc4"
KEY_LINE = "#3b4652"
LOGIC_LINE = "#8d97a3"

HEAD_H, ROW_H = 4.2, 2.6

# 테이블: 이름 → (x, 상단 y, 폭, 사용 여부, 행 수 표기, [(컬럼, 설명, 키)])
TABLES = {
    "LDAP": (67, 78, 26, True, "월별 18개 · 16,743행", [
        ("employee_name", "이름", ""),
        ("user_id", "사용자 ID", "PK"),
        ("email", "회사 메일", "UK"),
        ("role", "직무", ""),
        ("business_unit", "사업부", ""),
        ("functional_unit", "기능 조직", ""),
        ("department", "부서", ""),
        ("team", "팀", ""),
        ("supervisor", "상사", ""),
    ]),
    "psychometric": (118, 78, 26, False, "1,000행", [
        ("employee_name", "이름", ""),
        ("user_id", "사용자 ID", "PK·FK"),
        ("O", "개방성", ""),
        ("C", "성실성", ""),
        ("E", "외향성", ""),
        ("A", "친화성", ""),
        ("N", "신경성", ""),
    ]),
    "logon": (4, 40, 26, True, "854,859행", [
        ("id", "이벤트 ID", "PK"),
        ("date", "일시", ""),
        ("user", "사용자 ID", "FK"),
        ("pc", "PC", ""),
        ("activity", "Logon / Logoff", ""),
    ]),
    "email": (36, 40, 26, True, "1,314,400행", [
        ("id", "이벤트 ID", "PK"),
        ("date", "일시", ""),
        ("user", "사용자 ID", "FK"),
        ("pc", "PC", ""),
        ("to", "수신", ""),
        ("cc", "참조", ""),
        ("bcc", "숨은 참조", ""),
        ("from", "발신 주소", "FK"),
        ("size", "크기", ""),
        ("attachments", "첨부 수", ""),
        ("content", "본문 키워드", ""),
    ]),
    "http": (68, 40, 26, False, "1,422,900행", [
        ("id", "이벤트 ID", "PK"),
        ("date", "일시", ""),
        ("user", "사용자 ID", "FK"),
        ("pc", "PC", ""),
        ("url", "접속 주소", ""),
        ("content", "페이지 내용", ""),
    ]),
    "device": (100, 40, 26, False, "405,380행", [
        ("id", "이벤트 ID", "PK"),
        ("date", "일시", ""),
        ("user", "사용자 ID", "FK"),
        ("pc", "PC", ""),
        ("activity", "Connect / Disconnect", ""),
    ]),
    "file": (132, 40, 26, False, "445,581행", [
        ("id", "이벤트 ID", "PK"),
        ("date", "일시", ""),
        ("user", "사용자 ID", "FK"),
        ("pc", "PC", ""),
        ("filename", "파일명", ""),
        ("content", "파일 내용", ""),
    ]),
}


def row_y(name, col):
    x, top, w, used, count, cols = TABLES[name]
    i = [c[0] for c in cols].index(col)
    return top - HEAD_H - ROW_H * (i + 0.5)


def bottom(name):
    x, top, w, used, count, cols = TABLES[name]
    return top - HEAD_H - ROW_H * len(cols)


def center_x(name):
    x, top, w, *_ = TABLES[name]
    return x + w / 2


def draw_table(ax, name, slide=False):
    x, top, w, used, count, cols = TABLES[name]
    head, edge, body = (USED_HEAD, USED_EDGE, USED_BODY) if used else (UNUSED_HEAD, UNUSED_EDGE, UNUSED_BODY)
    h = HEAD_H + ROW_H * len(cols)
    ax.add_patch(FancyBboxPatch((x, top - h), w, h, boxstyle="round,pad=0,rounding_size=0.8",
                                fc=body, ec=edge, lw=1.6, zorder=3))
    ax.add_patch(FancyBboxPatch((x, top - HEAD_H), w, HEAD_H, boxstyle="round,pad=0,rounding_size=0.8",
                                fc=head, ec=edge, lw=1.6, zorder=4))
    ax.add_patch(Rectangle((x + 0.1, top - HEAD_H), w - 0.2, 1.0, fc=head, ec="none", zorder=4))
    ax.text(x + 1.2, top - HEAD_H / 2, name, fontsize=13, fontweight="bold", color="white",
            va="center", ha="left", zorder=5)
    badge = count if slide else ("사용 · " if used else "미사용 · ") + count
    ax.text(x + w - 1.2, top - HEAD_H / 2, badge, fontsize=8.5,
            color="white", va="center", ha="right", zorder=5)
    for i, (col, desc, key) in enumerate(cols):
        cy = top - HEAD_H - ROW_H * (i + 0.5)
        if i:
            ax.plot([x + 0.6, x + w - 0.6], [cy + ROW_H / 2] * 2, color="#e3e6ea", lw=0.8, zorder=4)
        if key:
            kc = PK_C if key.startswith("PK") else (UK_C if key == "UK" else FK_C)
            ax.text(x + 1.0, cy, key, fontsize=7.5, fontweight="bold", color=kc, va="center", ha="left", zorder=5)
        ax.text(x + 5.2, cy, col, fontsize=10, family="Consolas", color=INK,
                fontweight="bold" if key else "normal", va="center", ha="left", zorder=5)
        ax.text(x + w - 1.0, cy, desc, fontsize=8.5, color=MUTED, va="center", ha="right", zorder=5)


def end_marker(ax, p, d, kind, color):
    """p: 테이블 경계의 끝점, d: 테이블 안쪽을 향하는 단위벡터."""
    p, d = np.asarray(p, float), np.asarray(d, float)
    n = np.array([-d[1], d[0]])
    if kind == "many":  # 까마귀발
        q = p - d * 1.8
        for s in (-1, 0, 1):
            e = p + n * s * 1.1
            ax.plot([q[0], e[0]], [q[1], e[1]], color=color, lw=1.5, zorder=2, solid_capstyle="round")
    else:  # 하나 (세로 막대 두 개 = 정확히 1)
        for off in (1.0, 1.7):
            c = p - d * off
            a, b = c + n * 1.0, c - n * 1.0
            ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=1.5, zorder=2)


def path(ax, pts, color, dashed=False, start=None, end=None, lw=1.6):
    pts = np.asarray(pts, float)
    ax.plot(pts[:, 0], pts[:, 1], color=color, lw=lw, ls=(0, (4, 3)) if dashed else "-", zorder=2,
            solid_joinstyle="miter")
    if start:
        d = pts[0] - pts[1]
        end_marker(ax, pts[0], d / np.linalg.norm(d), start, color)
    if end:
        d = pts[-1] - pts[-2]
        end_marker(ax, pts[-1], d / np.linalg.norm(d), end, color)


def label(ax, x, y, text, color=KEY_LINE, ha="center", size=9):
    ax.text(x, y, text, fontsize=size, color=color, ha=ha, va="center", zorder=6, linespacing=1.35,
            bbox=dict(fc="white", ec="none", pad=1.2))


def render(slide=False):
    """slide=True: PPT용. 제목·메모와 헤더의 사용 여부 글자를 뺌 (색 구분·범례는 유지)."""
    top_y = 81 if slide else 100
    fig = plt.figure(figsize=(16, top_y / 10), dpi=150)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 160)
    ax.set_ylim(0, top_y)
    ax.set_aspect("equal")
    ax.axis("off")

    if not slide:
        ax.text(4, 95, "샘플 데이터 7종 ERD", fontsize=24, fontweight="bold", color=INK, va="center")
        ax.text(4, 90.3, "CERT r4.2 · 2010-01-02 ~ 2011-05-17 · 사용자 1,000명 · 점수 산출에는 LDAP · logon · email 3종을 사용",
                fontsize=12, color=MUTED, va="center")

    for name in TABLES:
        draw_table(ax, name, slide)

    # ── 키 조인 (실선) ──
    # LDAP 1 ── N 활동 로그 5종 : user_id = user
    bus_y = 45.2
    ldap_cx = center_x("LDAP")
    path(ax, [(ldap_cx, bottom("LDAP")), (ldap_cx, bus_y)], KEY_LINE, start="one")
    xs = [center_x(n) for n in ("logon", "email", "http", "device", "file")]
    ax.plot([min(xs), max(xs)], [bus_y, bus_y], color=KEY_LINE, lw=1.6, zorder=2)
    for cx in xs:
        path(ax, [(cx, bus_y), (cx, 40)], KEY_LINE, end="many")
    label(ax, 96, bus_y, "LDAP.user_id = user   ·   1 : N")

    # LDAP 1 ── 1 psychometric : user_id
    yl = row_y("LDAP", "user_id")
    path(ax, [(93, yl), (118, yl)], KEY_LINE, start="one", end="one")
    label(ax, 105.5, yl + 2.2, "user_id   ·   1 : 1")

    # LDAP.email 1 ── N email.from : 일치하면 회사 계정
    y_from = row_y("email", "from")
    y_mail = row_y("LDAP", "email")
    path(ax, [(67, y_mail), (65, y_mail), (65, y_from), (62, y_from)], FK_C, start="one", end="many")
    label(ax, 64, y_mail + 2.4, "LDAP.email = email.from\n일치 → 회사 계정 · 불일치 → 개인 계정 (37.7%)",
          color=FK_C, ha="right", size=8.5)

    # ── 논리 연결 (점선): 키가 아니라 user + pc + 시간 구간 ──
    low_y = 3.2
    path(ax, [(center_x("logon"), bottom("logon")), (center_x("logon"), low_y),
              (center_x("device"), low_y), (center_x("device"), bottom("device"))], LOGIC_LINE, dashed=True)
    for n in ("email", "http"):
        path(ax, [(center_x(n), low_y), (center_x(n), bottom(n))], LOGIC_LINE, dashed=True)
    label(ax, 97, low_y + 3.6, "logon 로그인 구간 안에서 발생\nuser + pc + 시간 · 활동의 99.99%", color=MUTED, size=8.5)

    yd = TABLES["device"][1] - HEAD_H - ROW_H * 2.0
    path(ax, [(126, yd), (132, yd)], LOGIC_LINE, dashed=True)
    label(ax, 129, yd - 4.0, "연결\n구간\n99.56%", color=MUTED, size=7.5)

    # ── 범례 ──
    lx, ly = 4, 76
    ax.text(lx, ly, "읽는 법", fontsize=11, fontweight="bold", color=INK, va="center")
    items = [
        ("key", PK_C, "PK", "기본 키"),
        ("key", FK_C, "FK", "외래 키 (다른 테이블 참조)"),
        ("key", UK_C, "UK", "고유 값 (사람당 회사 메일 1개)"),
        ("line", KEY_LINE, "solid", "키 조인"),
        ("line", LOGIC_LINE, "dashed", "논리 연결: 같은 user·pc의 시간 구간"),
        ("mark", KEY_LINE, "one", "1  (정확히 하나)"),
        ("mark", KEY_LINE, "many", "N  (여러 건)"),
        ("head", USED_HEAD, "", "점수 산출에 사용"),
        ("head", UNUSED_HEAD, "", "관계만 확인 · 점수 미사용"),
    ]
    for i, (kind, color, tag, text) in enumerate(items):
        yy = ly - 3.3 - i * 2.9
        if kind == "key":
            ax.text(lx + 1.5, yy, tag, fontsize=8.5, fontweight="bold", color=color, va="center", ha="center")
        elif kind == "line":
            ax.plot([lx, lx + 4], [yy, yy], color=color, lw=1.6, ls=(0, (4, 3)) if tag == "dashed" else "-")
        elif kind == "mark":
            ax.plot([lx, lx + 4], [yy, yy], color=color, lw=1.5)
            end_marker(ax, (lx + 4, yy), (1, 0), tag, color)
        else:
            ax.add_patch(FancyBboxPatch((lx, yy - 0.9), 4, 1.8, boxstyle="round,pad=0,rounding_size=0.4",
                                        fc=color, ec=color))
        ax.text(lx + 5.5, yy, text, fontsize=9.5, color=INK, va="center")

    if not slide:
        notes = ("· id는 파일별 번호 → 파일 간 조인 키 아님\n"
                 "· LDAP: 월별 스냅숏 18개 (PK = 월 + user_id)\n"
                 "· LDAP에는 pc 컬럼 없음\n"
                 "· device·file은 265명만 기록")
        ax.text(119, 54.3, notes, fontsize=8.5, color=MUTED, va="top", linespacing=1.55)

    stem = "03_데이터_ERD_슬라이드용" if slide else "02_데이터_ERD"
    fig.savefig(OUT / f"{stem}.png", dpi=150, facecolor="white")
    fig.savefig(OUT / f"{stem}.svg", facecolor="white")
    plt.close(fig)


render(slide=False)
render(slide=True)
print("saved", OUT)
