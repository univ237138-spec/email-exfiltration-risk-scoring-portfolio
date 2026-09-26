"""Figures comparing v2.2 statistical scoring with channel-wise Isolation Forest. Reads frozen experiment outputs only."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
EXP = ROOT / '20260922_210819_IsolationForest_채널별비교'
sys.path.insert(0, str(EXP))

# Reference palette (dataviz skill): categorical slots 1-3 validate all-pairs in light mode.
CUR, IFX, IFE = '#2a78d6', '#eb6834', '#1baf7a'
INK, INK2, MUTED, GRID, BASE, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7', '#fcfcfb'
NEUTRAL = '#c3c2b7'
BLUES = LinearSegmentedColormap.from_list('blues', ['#f0efec', '#cde2fb', '#86b6ef', '#3987e5', '#1c5cab', '#0d366b'])

plt.rcParams.update({
    'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 11,
    'figure.facecolor': SURF, 'axes.facecolor': SURF, 'savefig.facecolor': SURF,
    'text.color': INK, 'axes.labelcolor': INK2, 'xtick.color': MUTED, 'ytick.color': INK2,
    'axes.edgecolor': BASE, 'axes.titlecolor': INK,
})


def clean(ax, grid='x'):
    for s in ['top', 'right']:
        ax.spines[s].set_visible(False)
    ax.spines['left' if grid == 'x' else 'bottom'].set_color(BASE)
    ax.spines['bottom' if grid == 'x' else 'left'].set_visible(False)
    ax.grid(axis=grid, color=GRID, linewidth=.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def header(fig, title, subtitle, note=None):
    fig.text(.04, .955, title, fontsize=18, weight='bold', color=INK, va='top')
    fig.text(.04, .895, subtitle, fontsize=11, color=INK2, va='top', linespacing=1.5)
    if note:
        fig.text(.04, .03, note, fontsize=9.5, color=MUTED, va='bottom', linespacing=1.5)


def save(fig, name):
    fig.savefig(OUT / f'{name}.png', dpi=180)
    fig.savefig(OUT / f'{name}.svg')
    plt.close(fig)


def fig1_overall(fixed, eq):
    review = fixed.loc[fixed.channel.eq('review')].set_index('method')
    e = eq.set_index('metric')['mean']
    methods = [('기존 통계 모델 v2.2', CUR, review.loc['현재 v2.2']),
               ('IF 고정경계', IFX, review.loc['IF 고정경계']),
               ('IF 동일 조사량', IFE, dict(incident_users=e.incident_users, normal_users=e.normal_users,
                                         alert_days=e.alert_days))]
    panels = [('사건기간 탐지 내부자', 'incident_users', 70, '명', '많을수록 좋음'),
              ('비내부자 오탐 인원', 'normal_users', 905, '명', '적을수록 좋음'),
              ('조사 사용자·일', 'alert_days', None, '건', '조사량')]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.6))
    fig.subplots_adjust(left=.14, right=.97, top=.70, bottom=.2, wspace=.35)
    y = np.arange(3)[::-1]
    for ax, (title, key, denom, unit, hint) in zip(axes, panels):
        vals = [float(m[2][key]) for m in methods]
        ax.barh(y, vals, height=.56, color=[m[1] for m in methods], edgecolor=SURF, linewidth=2)
        for yi, v in zip(y, vals):
            lab = f'{v:,.0f}{unit}' + (f'  ({v / denom:.1%})' if denom else '')
            ax.text(v + max(vals) * .02, yi, lab, va='center', fontsize=11, color=INK)
        ax.set_xlim(0, max(vals) * 1.45)
        ax.set_yticks(y, [m[0] for m in methods] if ax is axes[0] else [''] * 3)
        ax.set_title(f'{title}\n', fontsize=13, weight='bold', loc='left')
        ax.text(0, 1.03, hint + (f' · 분모 {denom}명' if denom else ''), transform=ax.transAxes, fontsize=9.5, color=MUTED)
        clean(ax)
    header(fig, '같은 조사량(842건)에서 IF가 탐지 +4명, 오탐 -42명',
           '평가기간 2010-06-01~2011-05-17 · 이메일 경보 OR 로그온 경보 · 사용자는 한 번 이상 경보 시 1명으로 계산\n'
           '고정경계는 보정기간에 정한 경계를 그대로 적용해 경보량이 143건 늘었고, 이 경우 오탐도 26명 늘었다.',
           'IF 동일 조사량: 기존 채널별 경보량(이메일 498, 로그온 344)만큼 IF 상위 행을 선택한 사후 순위 비교(운영 경계 아님). '
           'IF 시드 0~4 모두 탐지 33명, 오탐 321~325명.\n기존 정답으로 정책을 검토한 이력이 있는 사후 비교이며 독립 검증 성능이 아님.')
    save(fig, '01_전체성능_비교')


def fig2_scenario(fixed):
    totals = {1: 30, 2: 30, 3: 10}
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.8), sharey=True)
    fig.subplots_adjust(left=.07, right=.97, top=.70, bottom=.2, wspace=.12)
    x = np.arange(3)
    w = .36
    for ax, (ch, title) in zip(axes, [('email', '이메일 채널'), ('logon', '로그온 채널'), ('review', '통합 조사 대상')]):
        f = fixed.loc[fixed.channel.eq(ch)].set_index('method')
        for off, (m, c, lab) in zip([-w / 2 - .01, w / 2 + .01], [('현재 v2.2', CUR, '기존'), ('IF 고정경계', IFX, 'IF')]):
            vals = [int(f.loc[m, f's{s}']) for s in (1, 2, 3)]
            ax.bar(x + off, vals, width=w, color=c, edgecolor=SURF, linewidth=2, label=lab)
            for xi, v in zip(x + off, vals):
                ax.text(xi, v + .6, str(v), ha='center', va='bottom', fontsize=11, color=INK)
        ax.set_xticks(x, [f'시나리오 {s}\n(내부자 {totals[s]}명)' for s in (1, 2, 3)])
        ax.set_title(title, fontsize=13, weight='bold', loc='left', pad=12)
        ax.set_ylim(0, 34)
        clean(ax, grid='y')
    axes[0].set_ylabel('사건기간 탐지 내부자 (명)')
    axes[0].legend(frameon=False, loc='upper left', fontsize=10.5)
    header(fig, 'IF의 이득은 시나리오 2(이메일), 손실은 시나리오 1(로그온)',
           '시나리오 1: 야간 로그온·이동식 저장장치 유출 · 시나리오 2: 구직 후 경쟁사 이직 전 유출 · 시나리오 3: 불만 시스템 관리자\n'
           '이메일 IF는 시나리오 2 탐지를 18명 → 30명으로 늘렸고, 로그온 IF는 시나리오 1 탐지 5명을 모두 잃었다.',
           '고정경계 기준. 평가기간 2010-06-01~2011-05-17. 통합 = 이메일 경보 OR 로그온 경보.')
    save(fig, '02_채널_시나리오별_탐지')


def fig3_change(per):
    order = [('IF만 탐지', IFX), ('기존만 탐지', CUR), ('둘 다 탐지', NEUTRAL), ('둘 다 미탐', '#e1e0d9')]
    fig, ax = plt.subplots(figsize=(13, 5.4))
    fig.subplots_adjust(left=.14, right=.97, top=.72, bottom=.25)
    y = np.arange(len(order))[::-1]
    for yi, (k, c) in zip(y, order):
        g = per.loc[per.change.eq(k)]
        n = len(g)
        ax.barh(yi, n, height=.58, color=c, edgecolor=SURF, linewidth=2)
        sc = g.scenario.astype(int).value_counts().sort_index()
        comp = ' · '.join(f'시나리오 {s} {v}명' for s, v in sc.items())
        ax.text(n + .5, yi, f'{n}명   {comp}', va='center', fontsize=11, color=INK)
    ax.set_yticks(y, [k for k, _ in order])
    ax.set_xlim(0, 52)
    ax.set_xlabel('내부자 수 (70명 중)')
    clean(ax)
    header(fig, 'IF가 11명을 새로 찾았지만 기존 탐지자 7명을 놓쳤다',
           '내부자 70명의 사건기간 탐지 여부를 두 모델로 나눈 결과 (고정경계)\n'
           'IF만 탐지 11명은 전원 시나리오 2, 기존만 탐지 7명은 시나리오 1 6명과 시나리오 3 1명이다.',
           'IF만 탐지: ABC0174, CCL0068, CEJ0109, CQW0652, EGD0132, FSC0601, IJM0776, MDH0580, PNL0301, RAR0725, TNM0961\n'
           '기존만 탐지: AJR0932, BDV0168, BTL0226, JMB0308, LQC0479, MCF0600 (시나리오 1), JTM0223 (시나리오 3)')
    save(fig, '03_내부자_탐지변화')


def fig4_hyper(grid):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.4))
    fig.subplots_adjust(left=.1, right=.9, top=.72, bottom=.17, wspace=.28)
    ms, nt = [256, 1024, 4096, 16384], [100, 300, 1000]
    chosen = {'email': (16384, 1000), 'logon': (256, 1000)}
    for ax, (ch, title) in zip(axes, [('email', '이메일 IF (입력 6개)'), ('logon', '로그온 IF (입력 2개)')]):
        g = grid.loc[grid.channel.eq(ch)].set_index(['max_samples', 'n_estimators'])
        mat = np.array([[g.loc[(m, n), 'S1_seed_jaccard'] for n in nt] for m in ms])
        im = ax.imshow(mat, cmap=BLUES, vmin=.55, vmax=1, aspect='auto')
        for i, m in enumerate(ms):
            for j, n in enumerate(nt):
                s1, s2 = g.loc[(m, n), 'S1_seed_jaccard'], g.loc[(m, n), 'S2_rate_transfer_err']
                dark = s1 > .86
                ax.text(j, i, f'{s1:.2f}\n오차 {s2:.2f}', ha='center', va='center', fontsize=10.5,
                        color='white' if dark else INK, linespacing=1.4)
                if (m, n) == chosen[ch]:
                    ax.add_patch(plt.Rectangle((j - .48, i - .48), .96, .96, fill=False, edgecolor=INK, linewidth=2.5))
                    ax.text(j + .46, i - .44, '선정', ha='right', va='top', fontsize=9, weight='bold',
                            color='white' if dark else INK)
        ax.set_xticks(range(3), [f'{n}' for n in nt])
        ax.set_yticks(range(4), [f'{m:,}' for m in ms])
        ax.set_xlabel('n_estimators (트리 수)')
        ax.set_ylabel('max_samples (트리당 표본)')
        ax.set_title(title, fontsize=13, weight='bold', loc='left', pad=10)
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
    cax = fig.add_axes([.925, .17, .012, .55])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label('S1 시드 안정성 (Jaccard)', color=INK2)
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=0, colors=MUTED)
    header(fig, '하이퍼파라미터: 이메일은 큰 표본, 로그온은 기본 표본이 안정적',
           '정답 미사용 · 2010-02~04 학습, 2010-05 검증 · 후보마다 시드 0~4로 5회 학습\n'
           '색과 큰 숫자 = 시드를 바꿔도 같은 날을 고르는 정도(S1), 오차 = 5월 경보율이 목표에서 벗어난 정도(S2)',
           '선정 규칙(사전 고정): S1 ≥ 최고-0.02 이고 S2 ≤ 최저+0.10 인 후보 중 계산량 최소. '
           '공통: max_features=1.0, bootstrap=False, 음수 z는 0으로 자름.\n'
           '이메일 기본값(256×100)은 시드만 바꿔도 경보 집합의 약 40%가 바뀜(S1 0.60).')
    save(fig, '04_하이퍼파라미터_탐색')


def fig5_profile(prof):
    cols = [('corp_ext_send_cnt', '외부 발송'), ('new_ext_rcpt_cnt', '신규 외부\n수신자'), ('corp_ext_att_mail_cnt', '외부 첨부'),
            ('personal_att_mail_cnt', '개인계정\n첨부'), ('jobkw_mail', '구직\n키워드'), ('night_mail', '새로운\n야간 메일'),
            ('other_pc_logon_cnt', '다른 PC\n로그온'), ('night_logon_cnt', '야간\n로그온')]
    prof = prof.set_index('group').loc[['둘 다 경보', '기존만 경보' if '기존만 경보' in prof.group.values else '현재만 경보', 'IF만 경보']]
    mat = np.array([[prof.loc[g, f'share_{c}'] * 100 for c, _ in cols] for g in prof.index])
    fig, ax = plt.subplots(figsize=(14, 5.6))
    fig.subplots_adjust(left=.2, right=.97, top=.70, bottom=.2)
    ax.imshow(mat, cmap=BLUES, vmin=0, vmax=55, aspect='auto')
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat[i, j]
            ax.text(j, i, f'{v:.0f}%', ha='center', va='center', fontsize=12, color='white' if v > 30 else INK,
                    weight='bold' if (i == 2 and j in (4, 5)) else 'normal')
    labels = []
    for g in prof.index:
        r = prof.loc[g]
        name = '기존만 경보' if g == '현재만 경보' else g
        labels.append(f'{name}\n{int(r.days)}일 · 사건기간 {int(r.incident_days)}일')
    ax.set_yticks(range(3), labels)
    ax.set_xticks(range(len(cols)), [l for _, l in cols])
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.axvline(5.5, color=SURF, linewidth=4)
    header(fig, 'IF만 경보한 날의 32%가 구직 키워드, 31%가 새로운 야간 메일',
           '경보일 그룹별로 각 지표가 기존 모델의 1점 수준(보정기간 99% 분위수 이상, 규칙형은 발생)에 도달한 비율\n'
           '기존만 경보한 날은 외부 발송·개인계정 첨부 같은 건수 지표 급증이 많고, 구직 키워드는 0%였다.',
           '평가기간 통합 조사 대상 기준. 새로운 야간 메일 IF 경보 160일 중 95.6%가 비내부자 — IF 오탐 증가의 주요 원인.\n'
           '구직 키워드: 평가기간 189일 전부 IF 경보, 기존 모델 주의 이상은 26일(단독 2점 < 조사 경계 3점).')
    save(fig, '05_불일치경보일_지표프로필')


def fig6_cases():
    from if_common import load
    d = load().drop(columns='cal').merge(pd.read_parquet(EXP / 'if_scores.parquet'), on=['user', 'date'])
    cases = [('EGD0132', '시나리오 2 · IF만 사건기간 탐지', '2010-08-02', '2010-09-28', '2010-07-12', '2010-10-08'),
             ('AJR0932', '시나리오 1 · 기존만 사건기간 탐지', '2010-09-10', '2010-09-18', '2010-08-25', '2010-10-02')]
    fig, axes = plt.subplots(2, 1, figsize=(14, 7.4))
    fig.subplots_adjust(left=.14, right=.97, top=.74, bottom=.12, hspace=.7)
    rows = [('기존 경보', 'cur_review', CUR, 'o'), ('IF 경보', 'if_review', IFX, 'D'),
            ('구직 키워드 메일', 'jobkw_mail_flag', INK2, '|'), ('야간 로그온 증가 (z>0)', 'night_logon_up', MUTED, '|')]
    for ax, (u, desc, s, e, lo, hi) in zip(axes, cases):
        q = d.loc[d.user.eq(u) & d.date.between(lo, hi)].copy()
        q['night_logon_up'] = q.night_logon_cnt_z.gt(0)
        ax.axvspan(pd.Timestamp(s), pd.Timestamp(e) + pd.DateOffset(days=1), color='#f0efec', zorder=0)
        ax.text(pd.Timestamp(s), len(rows) - .35, ' 사건기간', fontsize=9.5, color=INK2, va='bottom')
        for i, (lab, col, c, mk) in enumerate(rows):
            yi = len(rows) - 1 - i
            hit = q.loc[q[col].astype(bool), 'date']
            ax.scatter(hit, [yi] * len(hit), s=70 if mk != '|' else 160, marker=mk, color=c,
                       edgecolor=SURF if mk != '|' else None, linewidth=2 if mk != '|' else 2.2, zorder=3)
        ax.set_yticks(range(len(rows))[::-1], [r[0] for r in rows])
        ax.set_ylim(-.6, len(rows) - .1)
        ax.set_xlim(pd.Timestamp(lo), pd.Timestamp(hi))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.set_title(f'{u}  ·  {desc}', fontsize=12.5, weight='bold', loc='left', pad=8)
        clean(ax, grid='x')
    axes[0].annotate('7-26 신규 외부 수신자 z 4.87\n기존 3점 주의, IF는 경계 아래', xy=(pd.Timestamp('2010-07-26'), 3),
                     xytext=(pd.Timestamp('2010-07-13'), 0.1), fontsize=9.5, color=INK2,
                     arrowprops=dict(arrowstyle='-', color=MUTED, lw=1))
    axes[1].annotate('9-10 야간 로그온 z 2.00 (단일 지표)\n기존 경보, IF는 보정 상위 0.55%로 경계 아래',
                     xy=(pd.Timestamp('2010-09-10'), 3), xytext=(pd.Timestamp('2010-09-19'), 1.6), fontsize=9.5,
                     color=INK2, arrowprops=dict(arrowstyle='-', color=MUTED, lw=1))
    header(fig, '사례: 구직 키워드가 나온 날은 IF만, 단일 지표 급증은 기존 모델만 경보',
           '사전 규칙으로 고른 사례 사용자 · 회색 영역 = 정답 사건기간\n'
           'EGD0132는 사건기간 중 구직 키워드 6일을 IF만 경보했고, AJR0932의 야간 로그온 급증은 기존 로그온 규칙만 잡았다.',
           '사례는 전체 성능 차이를 설명하는 보조 자료이며 모델 우열의 근거가 아님. 전체 날짜표: 20260922_210819_IsolationForest_채널별비교/case_*.csv')
    save(fig, '06_사례_타임라인')


def main():
    fixed = pd.read_csv(EXP / 'fixed_threshold_metrics.csv')
    eq = pd.read_csv(EXP / 'equal_volume_summary.csv')
    per = pd.read_csv(EXP / 'incident_detection_by_user.csv')
    per['change'] = per.change.replace({'현재만 탐지': '기존만 탐지'})
    grid = pd.read_csv(EXP / 'hyperparameter_search.csv')
    prof = pd.read_csv(EXP / 'disagreement_profile.csv')
    prof['group'] = prof.group.replace({'현재만 경보': '기존만 경보'})
    fig1_overall(fixed, eq)
    fig2_scenario(fixed)
    fig3_change(per)
    fig4_hyper(grid)
    fig5_profile(prof)
    fig6_cases()


if __name__ == '__main__':
    main()
