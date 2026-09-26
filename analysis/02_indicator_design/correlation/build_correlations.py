"""Read-only source analysis. Run with Python; outputs are beside this script."""
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import sys
import json
import hashlib
import itertools
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))
from scoring import CORE, LOGON, points, VERSION

KEYS = ['corp_ext_send_cnt', 'new_ext_rcpt_cnt', 'corp_ext_att_mail_cnt',
        'personal_att_mail_cnt', 'int_rcpt_cnt', 'jobkw_mail', 'night_mail',
        'other_pc_logon_cnt', 'night_logon_cnt']
NAMES = ['회사계정 외부 발송', '신규 외부 수신자', '회사계정 외부 첨부',
         '개인계정 첨부', '사내 수신자 [제외]', '구직 키워드 메일',
         '야간 메일', '다른 PC 로그온', '야간 로그온']
LABEL = dict(zip(KEYS, NAMES))
plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False,
                     'font.size': 11, 'figure.facecolor': '#ffffff'})

def save_csv(df, name, index=True):
    df.to_csv(OUT / name, index=index, encoding='utf-8-sig')

def heatmap(corr, title, subtitle, filename, scoring=False):
    n = len(corr)
    labels = [LABEL[k].replace('야간 메일', '새로운 야간 메일') if scoring and k == 'night_mail' else LABEL[k] for k in corr]
    fig, ax = plt.subplots(figsize=(12.6, 10.8))
    fig.subplots_adjust(left=.22, right=.89, top=.84, bottom=.22)
    im = ax.imshow(corr, cmap='RdBu_r', vmin=-1, vmax=1)
    ax.set_xticks(range(n), labels, rotation=40, ha='right', rotation_mode='anchor')
    ax.set_yticks(range(n), labels)
    ax.set_xticks(np.arange(-.5, n, 1), minor=True)
    ax.set_yticks(np.arange(-.5, n, 1), minor=True)
    ax.grid(which='minor', color='white', linewidth=2)
    ax.tick_params(which='both', length=0, pad=10)
    for i in range(n):
        for j in range(n):
            v = corr.iloc[i, j]
            ax.text(j, i, f'{v:.2f}' if abs(v) >= .005 else '0.00', ha='center', va='center',
                    color='white' if abs(v) > .6 else '#172b42', fontsize=12,
                    weight='bold' if i != j and abs(v) >= .3 else 'normal')
    for tick, k in zip(ax.get_xticklabels(), corr):
        if k == 'int_rcpt_cnt': tick.set_color('#a26118')
    for tick, k in zip(ax.get_yticklabels(), corr):
        if k == 'int_rcpt_cnt': tick.set_color('#a26118')
    for s in ax.spines.values(): s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=.045, pad=.035, ticks=[-1, -.5, 0, .5, 1])
    cb.set_label('반대 방향  ←  상관계수  →  같은 방향', labelpad=12)
    fig.text(.08, .95, title, fontsize=22, weight='bold', color='#172b42')
    fig.text(.08, .902, subtitle, fontsize=11, color='#526273')
    fig.text(.08, .04, '빨강: 함께 증가 · 파랑: 반대로 변화 · 흰색: 관계가 약함 | 대각선 1.00은 자기 자신과의 상관\n상관은 인과·탐지 성능을 뜻하지 않으며, 0에 가까워도 독립이라고 단정할 수 없습니다.', fontsize=10, color='#526273')
    fig.savefig(OUT / (filename + '.png'), dpi=180)
    fig.savefig(OUT / (filename + '.svg'))
    plt.close(fig)

def main():
    source = PROJECT_ROOT / "outputs/datasets/생성지표/user_day_baseline_30.csv"
    df = pd.read_csv(source, parse_dates=['date'])
    assert not df.duplicated(['user', 'date']).any()
    assert df.is_scored.eq((df.active_day_seq.gt(10) & df.days_since_first.ge(30)).astype(int)).all()
    d = df.loc[df.is_scored.eq(1)].copy()
    meta = json.loads((PROJECT_ROOT / "outputs/dashboard/metadata.json").read_text(encoding='utf-8'))
    assert meta['source']['version'] == VERSION
    raw = pd.DataFrame({k: d[k if k not in ('jobkw_mail', 'night_mail') else k + '_cnt'] for k in KEYS})
    inp = pd.DataFrame({k: d[k + '_z'] if k not in ('jobkw_mail', 'night_mail') else
                        (d.jobkw_mail_flag if k == 'jobkw_mail' else (d.night_mail_flag.eq(1) & d.night_mail_past30.eq(0)).astype(int)) for k in KEYS})
    current = [k for k in KEYS if k != 'int_rcpt_cnt']
    score = pd.DataFrame({k: points(d[k + '_z'], meta['thresholds'][k]) if k in CORE | LOGON else
                          inp[k] * meta['policy']['job_points' if k == 'jobkw_mail' else 'night_points'] for k in current})
    for frame in [raw, inp, score]:
        assert np.isfinite(frame.to_numpy()).all()
        assert frame.nunique().gt(1).all()
    cached = pd.read_parquet(PROJECT_ROOT / "outputs/dashboard/scored.parquet")
    check = d[['user', 'date']].join(score.add_suffix('_recomputed')).merge(
        cached[['user', 'date'] + [k + '_points' for k in current]], on=['user', 'date'], validate='one_to_one')
    assert len(check) == len(d)
    for k in current:
        assert check[k + '_recomputed'].eq(check[k + '_points']).all(), k
    mats = {'raw_pearson': raw.corr(), 'raw_spearman': raw.corr(method='spearman'),
            'input_pearson': inp.corr(), 'input_spearman': inp.corr(method='spearman'),
            'points_pearson': score.corr(), 'points_spearman': score.corr(method='spearman'),
            'raw_within_user_pearson': (raw - raw.groupby(d.user).transform('mean')).corr()}
    for period, mask in [('calibration', d.date.le('2010-05-31')), ('post_calibration', d.date.gt('2010-05-31'))]:
        for name, frame in [('raw', raw), ('input', inp), ('points', score)]:
            mats[period + '_' + name + '_pearson'] = frame.loc[mask].corr()
    for name, mat in mats.items():
        assert np.allclose(mat, mat.T) and np.allclose(np.diag(mat), 1)
        save_csv(mat.rename(index=LABEL, columns=LABEL), name + '.csv')
    base = f'{len(d):,} 사용자·일 · {d.user.nunique():,}명 · {d.date.min():%Y-%m-%d} ~ {d.date.max():%Y-%m-%d}'
    heatmap(mats['raw_pearson'], '기존 9개 행동지표 | 행동량의 상관관계', base + '\nPearson · 당일 원건수 기준 · 사내 수신자는 현재 점수에서 제외', '01_raw_pearson')
    heatmap(mats['raw_spearman'], '기존 9개 행동지표 | 순위로 다시 확인', base + '\nSpearman · 큰 값의 영향에 덜 민감 · 0이 많은 지표는 공동 순위가 많음', '02_raw_spearman')
    heatmap(mats['input_pearson'], '기존 9개 지표 | 평소 대비 변화의 상관관계', base + '\nPearson · 건수형은 개인 기준선 z · 규칙형은 실제 점수 발생 조건(0/1)', '03_scoring_input', True)
    heatmap(mats['points_pearson'], '현재 8개 점수지표 | 점수 중복 확인', base + '\nPearson · 실제 개별 지표 점수 · 로그온 2개는 합산하지 않고 최댓값 사용', '04_actual_points', True)
    rows = []
    for a, b in itertools.combinations(KEYS, 2):
        r = {'a': LABEL[a], 'b': LABEL[b]}
        for name, mat in mats.items():
            r[name] = mat.loc[a, b] if a in mat and b in mat else np.nan
        if a in score and b in score:
            aa, bb = score[a].gt(0), score[b].gt(0)
            both = int((aa & bb).sum())
            r.update(a_positive=int(aa.sum()), b_positive=int(bb.sum()), both_positive=both,
                     b_given_a=both / aa.sum(), a_given_b=both / bb.sum(),
                     jaccard=both / (aa | bb).sum())
        rows.append(r)
    pairs = pd.DataFrame(rows).sort_values('raw_pearson', key=lambda s: s.abs(), ascending=False)
    save_csv(pairs, 'all_36_pairs.csv', False)
    stats = pd.DataFrame({'지표': NAMES, '원건수_0비율': raw.eq(0).mean().values,
                          '원건수_평균': raw.mean().values, '원건수_최댓값': raw.max().values,
                          '현재점수발생_행수': [int(score[k].gt(0).sum()) if k in score else np.nan for k in KEYS]})
    save_csv(stats, 'indicator_summary.csv', False)
    info = {'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'version': VERSION, 'eligible_rows': len(d), 'excluded_rows': len(df)-len(d), 'users': int(d.user.nunique()),
            'date_min': str(d.date.min().date()), 'date_max': str(d.date.max().date()),
            'calibration_rows': int(d.date.le('2010-05-31').sum()), 'post_calibration_rows': int(d.date.gt('2010-05-31').sum()),
            'thresholds': meta['thresholds'], 'policy': meta['policy'], 'cached_points_match': True,
            'attachment_subset_violations': int(raw.corp_ext_att_mail_cnt.gt(raw.corp_ext_send_cnt).sum())}
    (OUT / 'analysis_metadata.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print(pairs[['a','b','raw_pearson','raw_spearman','input_pearson','points_pearson','raw_within_user_pearson','both_positive','b_given_a','a_given_b']].head(15).to_string(index=False))

if __name__ == '__main__':
    main()
