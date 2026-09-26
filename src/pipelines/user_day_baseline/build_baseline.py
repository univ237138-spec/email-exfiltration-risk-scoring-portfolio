"""Reproducible user x calendar-day features and past-only personal baselines.

No labels/answers/labels or psychometric values enter behavior features/baselines.
Run from the data directory: python src/pipelines/user_day_baseline/build_baseline.py
"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
from time import perf_counter
from urllib.parse import urlsplit

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SOURCES = ('logon', 'device', 'file', 'email', 'http')
KEY = ['user', 'date']
FEATURES = [
    'total_event_count', 'all_pc_count', 'active_hour_count',
    'after_hours_event_count', 'after_hours_event_ratio',
    'first_event_minute', 'last_event_minute',
    'logon_count', 'logon_after_hours_count', 'logon_pc_count',
    'device_connect_count', 'device_after_hours_count',
    'file_event_count', 'file_unique_filename_count', 'file_after_hours_count',
    'file_archive_count', 'file_executable_count',
    'email_event_count', 'email_ldap_sender_match_count',
    'email_external_recipient_event_count', 'email_ldap_sender_external_event_count',
    'email_size_sum', 'email_size_mean', 'email_attachment_count',
    'email_with_attachment_count', 'email_unique_recipient_count',
    'email_external_recipient_count', 'email_bcc_event_count', 'email_after_hours_count',
    'http_event_count', 'http_unique_host_count', 'http_after_hours_count',
    'new_pc_count', 'http_new_host_count',
]


def log(message):
    print(message, flush=True)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def read_ldap(root):
    frames = []
    for path in sorted((PROJECT_ROOT / "inputs/LDAP").glob('*.csv')):
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        df['snapshot_month'] = path.stem
        frames.append(df.rename(columns={'user_id': 'user'}))
    ldap = pd.concat(frames, ignore_index=True)
    if ldap.duplicated(['user', 'snapshot_month']).any():
        raise ValueError('LDAP has duplicate user/month keys')
    ldap['email'] = ldap['email'].str.strip().str.lower()
    return ldap


def recipient_addresses(row):
    # Count a recipient once per event even if repeated in to/cc/bcc.
    return sorted({s.strip().lower() for value in row for s in value.split(';') if s.strip()})


def aggregate_source(root, source, ldap, args):
    cols = ['id', 'date', 'user', 'pc'] + {
        'logon': ['activity'], 'device': ['activity'], 'file': ['filename'],
        'email': ['to', 'cc', 'bcc', 'from', 'size', 'attachments'], 'http': ['url'],
    }[source]
    df = pd.read_csv(root / f'{source}.csv', usecols=cols, keep_default_na=False,
                     dtype={c: str for c in cols if c not in ('size', 'attachments')})
    rows = len(df)
    duplicate_ids = int(df['id'].duplicated().sum())
    bad_keys = int(df[['id', 'user', 'pc', 'date']].apply(lambda x: x.str.strip().eq('')).any(axis=1).sum())
    if duplicate_ids or bad_keys:
        raise ValueError(f'{source}: duplicate IDs={duplicate_ids}, empty keys={bad_keys}; resolve before aggregation')
    df['ts'] = pd.to_datetime(df['date'], format='%m/%d/%Y %H:%M:%S', errors='raise')
    df['date'] = df['ts'].dt.normalize()
    df['hour'] = df['ts'].dt.hour
    df['minute'] = df['hour'] * 60 + df['ts'].dt.minute + df['ts'].dt.second / 60
    df['after_hours'] = (df['hour'] < args.work_start) | (df['hour'] >= args.work_end)
    qc = dict(rows=rows, users=df.user.nunique(), duplicate_ids=duplicate_ids, empty_keys=bad_keys,
              min_timestamp=str(df.ts.min()), max_timestamp=str(df.ts.max()),
              numeric_totals={}, activity_counts={})
    if source in ('logon', 'device'):
        qc['activity_counts'] = df.activity.value_counts().to_dict()
        expected = {'Logon', 'Logoff'} if source == 'logon' else {'Connect', 'Disconnect'}
        if not set(df.activity.unique()).issubset(expected):
            raise ValueError(f'Unknown {source} activity')
    pcs = df[KEY + ['pc']].drop_duplicates()
    hours = df[KEY + ['hour']].drop_duplicates()
    coverage = df.groupby('date').size().rename(source + '_raw_event_count')
    g = df.groupby(KEY, sort=False)
    daily = g.agg(**{
        source + '_event_count': ('id', 'size'),
        source + '_pc_count': ('pc', 'nunique'),
        source + '_after_hours_count': ('after_hours', 'sum'),
        source + '_first_minute': ('minute', 'min'),
        source + '_last_minute': ('minute', 'max'),
    })
    count_cols = [c for c in daily if not c.endswith('_minute')]

    def add(column, values, method='sum', zero=True):
        df['_value'] = values
        daily[column] = df.groupby(KEY, sort=False)['_value'].agg(method)
        if zero:
            count_cols.append(column)

    if source == 'logon':
        add('logon_count', df.activity.eq('Logon'))
        add('logoff_count', df.activity.eq('Logoff'))
        add('logon_login_after_hours_count', df.activity.eq('Logon') & df.after_hours)
        add('logon_first_login_minute', df.minute.where(df.activity.eq('Logon')), 'min', False)
        add('logon_last_logoff_minute', df.minute.where(df.activity.eq('Logoff')), 'max', False)
    elif source == 'device':
        add('device_connect_count', df.activity.eq('Connect'))
        add('device_disconnect_count', df.activity.eq('Disconnect'))
        add('device_connect_after_hours_count', df.activity.eq('Connect') & df.after_hours)
    elif source == 'file':
        add('file_unique_filename_count', df.filename, 'nunique')
        ext = df.filename.str.rsplit('.', n=1).str[-1].str.lower()
        add('file_unique_extension_count', ext, 'nunique')
        add('file_archive_count', ext.isin(['zip', 'rar', '7z', 'gz', 'tar']))
        add('file_executable_count', ext.isin(['exe', 'dll', 'bat', 'cmd', 'ps1', 'msi']))
    elif source == 'email':
        for col in ('size', 'attachments'):
            df[col] = pd.to_numeric(df[col], errors='raise')
            if df[col].isna().any() or (df[col] < 0).any() or (df[col] % 1 != 0).any():
                raise ValueError(f'Invalid email {col}')
            qc['numeric_totals'][col] = int(df[col].sum())
        # Exact current-month match; never replace a missing month by a future snapshot.
        lookup = ldap.set_index(['user', 'snapshot_month']).email
        idx = pd.MultiIndex.from_arrays([df.user, df.date.dt.strftime('%Y-%m')])
        expected = pd.Series(lookup.reindex(idx).to_numpy(), index=df.index)
        sender_match = df['from'].str.strip().str.lower().eq(expected)
        addresses = df[['to', 'cc', 'bcc']].apply(recipient_addresses, axis=1)
        external = addresses.map(lambda row: [a for a in row if a.rsplit('@', 1)[-1] not in args.internal_domains])
        add('email_ldap_address_available_count', expected.notna())
        add('email_ldap_sender_match_count', sender_match)
        add('email_external_recipient_event_count', external.str.len().gt(0))
        add('email_ldap_sender_external_event_count', sender_match & external.str.len().gt(0))
        add('email_recipient_count', addresses.str.len())
        add('email_external_recipient_count', external.str.len())
        add('email_bcc_event_count', df.bcc.str.strip().ne(''))
        add('email_size_sum', df['size'])
        add('email_size_mean', df['size'], 'mean', False)
        add('email_size_max', df['size'], 'max', False)
        add('email_attachment_count', df.attachments)
        add('email_with_attachment_count', df.attachments.gt(0))
        recipients = df[KEY].assign(address=addresses).explode('address').dropna(subset=['address'])
        daily['email_unique_recipient_count'] = recipients.groupby(KEY).address.nunique()
        count_cols.append('email_unique_recipient_count')
    elif source == 'http':
        df['host'] = df.url.map(lambda u: (urlsplit(u).hostname or '').lower())
        qc['empty_host_count'] = int(df.host.eq('').sum())
        add('http_unique_host_count', df.host.where(df.host.ne('')), 'nunique')
        # First-seen uses only dates <= the current day. Multiple accesses on first day count once.
        first = df.loc[df.host.ne('')].groupby(['user', 'host']).date.min().reset_index()
        daily['http_new_host_count'] = first.groupby(KEY).size()
        count_cols.append('http_new_host_count')
    daily[count_cols] = daily[count_cols].fillna(0)
    qc['aggregated_event_count'] = int(daily[source + '_event_count'].sum())
    assert qc['aggregated_event_count'] == rows
    log(f'{source}: {rows:,} events -> {len(daily):,} observed user-days')
    return daily, pcs, hours, coverage, qc, count_cols


def rolling_one_user(frame, features, window_days, min_weekday, min_weekend):
    """For date t use eligible same-day-type rows in [t-window_days, t)."""
    chunks = []
    for day_type, part in frame.groupby('day_type', sort=False):
        part = part.sort_values('date').set_index('date')
        minimum = min_weekend if day_type == 'weekend' else min_weekday
        values = part[features].astype(float).where(part.baseline_eligible, np.nan)
        rolling = values.rolling(f'{window_days}D', closed='left', min_periods=1)
        counts = rolling.count().fillna(0)
        enough = counts >= minimum
        data = {
            'n': counts,
            'mean': rolling.mean().where(enough),
            'std': rolling.std(ddof=1).where(enough),
            'median': rolling.median().where(enough),
            'q25': rolling.quantile(.25).where(enough),
            'q75': rolling.quantile(.75).where(enough),
            'p95': rolling.quantile(.95).where(enough),
        }
        stats = pd.concat({stat: val.astype('float32') for stat, val in data.items()}, axis=1)
        stats.columns = [f'{feat}__{stat}' for stat, feat in stats.columns]
        meta = part[['user', 'day_type', 'baseline_eligible']].copy()
        meta['history_days'] = counts[features[0]].astype('int16')
        meta['minimum_history_days'] = minimum
        meta['baseline_ready'] = meta.history_days >= minimum
        meta['window_start'] = meta.index - np.timedelta64(window_days, 'D')
        meta['window_end_exclusive'] = meta.index
        chunks.append(pd.concat([meta, stats], axis=1).reset_index())
    return pd.concat(chunks, ignore_index=True).sort_values('date')


def write_rolling(daily, out, args):
    writer = None
    pending = []
    ready = 0
    ready_eligible = 0
    rows = 0
    try:
        for i, (_, frame) in enumerate(daily.groupby('user', sort=True), 1):
            result = rolling_one_user(frame, FEATURES, args.window_days, args.min_weekday, args.min_weekend)
            ready += int(result.baseline_ready.sum())
            ready_eligible += int((result.baseline_ready & result.baseline_eligible).sum())
            rows += len(result)
            pending.append(result)
            if len(pending) == 25:
                table = pa.Table.from_pandas(pd.concat(pending, ignore_index=True), preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(out / 'rolling_baseline.parquet', table.schema, compression='zstd')
                writer.write_table(table)
                pending.clear()
            if i % 100 == 0:
                log(f'Past-only rolling baseline: {i:,} users')
        if pending:
            table = pa.Table.from_pandas(pd.concat(pending, ignore_index=True), preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(out / 'rolling_baseline.parquet', table.schema, compression='zstd')
            writer.write_table(table)
    finally:
        if writer:
            writer.close()
    assert rows == len(daily)
    return dict(rows=rows, ready_rows=ready, ready_and_eligible_rows=ready_eligible,
                feature_count=len(FEATURES), statistics=['n', 'mean', 'std', 'median', 'q25', 'q75', 'p95'])


def feature_dictionary(daily):
    exact = {
        'user': '사용자 ID. 모든 결과의 키는 user + date',
        'date': '원본 시각의 달력 날짜. 시간대 변환 없음',
        'snapshot_month': '해당 날짜와 같은 월의 LDAP 스냅샷. 월초 유효 가정',
        'ldap_present': '해당 월 LDAP 명단에 존재. 정확한 일별 재직 상태는 아님',
        'has_activity': '5종 로그 중 1건 이상 관찰',
        'no_observed_activity': '해당 사용자·날짜에서 모든 로그 건수가 0',
        'baseline_eligible': 'LDAP에 존재하고 5종 모두 내부 관찰일인 날짜. 이 날짜만 과거 기준 학습에 포함',
        'all_sources_observed_interior': '모든 소스에 전역 이벤트가 있고 각 소스의 첫날/마지막날이 아님. 수집 완전성 보증은 아님',
        'total_event_count': '5종 소스 이벤트 수의 합. 소스 간 동일 행위를 병합한 횟수가 아님',
        'all_pc_count': '5종 소스 통합 후 user/date 내 고유 PC 수',
        'active_hour_count': '5종 통합 후 이벤트가 관찰된 서로 다른 시(0~23)의 개수. 활동시간 길이가 아님',
        'new_pc_count': '이 사용자의 과거 날짜에 없었던 고유 PC 수. 최초 관찰일에는 모든 PC가 신규',
        'http_new_host_count': '이 사용자의 과거 날짜에 없었던 고유 웹 호스트 수. 최초 관찰일에는 모두 신규',
        'after_hours_event_count': '설정된 시각 구간 밖의 5종 이벤트 수. 주말 여부와 별도',
        'after_hours_event_ratio': 'after_hours_event_count / total_event_count. 무활동일은 결측',
        'observed_span_minutes': '마지막 이벤트 - 첫 이벤트 분 차이. 실제 근무/세션 길이가 아님',
        'email_ldap_address_available_count': '해당 월 LDAP 주소가 존재하는 이메일 이벤트 수',
        'email_ldap_sender_match_count': 'from과 해당 월 LDAP 이메일이 일치하는 이벤트 수. 발송 추정 보조 지표',
        'email_external_recipient_event_count': 'to/cc/bcc에 내부 도메인 이외 주소가 1개 이상 있는 이벤트 수. 방향 미확정',
        'email_ldap_sender_external_event_count': 'LDAP 발신자 일치이면서 외부 수신자 주소가 있는 이벤트 수. 실제 유출 확정 아님',
        'email_recipient_count': '이벤트 내 to/cc/bcc 중복 제거 수신자 수를 날짜 단위로 합산',
        'email_external_recipient_count': '이벤트 내 중복 제거 외부 수신자 수를 날짜 단위로 합산',
        'email_unique_recipient_count': '날짜 전체 to/cc/bcc 중복 제거 주소 수',
        'email_bcc_event_count': 'bcc가 비어 있지 않은 이메일 이벤트 수',
        'email_attachment_count': 'attachments 합계. 첨부파일 용량 아님',
        'email_with_attachment_count': 'attachments > 0인 이메일 이벤트 수',
        'email_size_sum': '원본 size 합계. 단위 미확정; 전송/유출 바이트로 해석하지 않음',
        'email_size_mean': '원본 size 평균. 이메일 없는 날은 결측',
        'email_size_max': '원본 size 최대. 이메일 없는 날은 결측',
        'file_unique_filename_count': '원본 파일명 문자열의 고유 개수. 파일 식별자/해시가 아님',
        'file_unique_extension_count': '파일명 확장자의 고유 개수(소문자)',
        'file_archive_count': 'zip/rar/7z/gz/tar 확장자 파일 이벤트 수',
        'file_executable_count': 'exe/dll/bat/cmd/ps1/msi 확장자 파일 이벤트 수',
        'http_unique_host_count': 'URL hostname 고유 개수. 하위 도메인을 분리하며 등록 도메인으로 축약하지 않음',
        'logon_count': 'activity=Logon 건수', 'logoff_count': 'activity=Logoff 건수',
        'device_connect_count': 'activity=Connect 건수', 'device_disconnect_count': 'activity=Disconnect 건수',
        'logon_login_after_hours_count': 'Logon 중 설정 시각 구간 밖 이벤트 수',
        'device_connect_after_hours_count': 'Connect 중 설정 시각 구간 밖 이벤트 수',
        'weekday': '월요일=0 ~ 일요일=6', 'is_weekend': '토요일/일요일 여부. 공휴일 달력 미반영',
        'day_type': 'weekday 또는 weekend',
    }
    rows = []
    for c in daily:
        description = exact.get(c)
        if description is None:
            if c.endswith('_first_minute') or c == 'first_event_minute' or c == 'logon_first_login_minute':
                description = '해당 소스/행위의 첫 이벤트 시각(자정 이후 분, 초/60 포함). 이벤트 없으면 결측'
            elif c.endswith('_last_minute') or c == 'last_event_minute' or c == 'logon_last_logoff_minute':
                description = '해당 소스/행위의 마지막 이벤트 시각(자정 이후 분, 초/60 포함). 이벤트 없으면 결측'
            elif c.endswith('_after_hours_count'):
                description = '해당 소스의 설정 시각 구간 밖 이벤트 수(로그인 소스는 Logon+Logoff, 장치는 Connect+Disconnect)'
            elif c.endswith('_event_count'):
                description = '해당 소스 원본 이벤트 행 수'
            elif c.endswith('_pc_count'):
                description = '해당 소스의 날짜별 고유 PC 수'
            else:
                description = '해당 월 LDAP 원본 조직/직원 속성. 행동 이상치 계산에서 제외'
        rows.append(dict(column=c, dtype=str(daily[c].dtype), used_in_rolling_baseline=c in FEATURES,
                         description=description, missing_count=int(daily[c].isna().sum())))
    return pd.DataFrame(rows)


def build(args):
    started = perf_counter()
    root, out = args.data_dir.resolve(), args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    ldap = read_ldap(root)
    psych = pd.read_csv(PROJECT_ROOT / "inputs/events/psychometric.csv").rename(columns={'user_id': 'user'})
    if psych.user.duplicated().any():
        raise ValueError('Duplicate psychometric users')
    psych.to_csv(out / 'psychometric_context_only.csv', index=False, encoding='utf-8-sig')
    ldap.to_parquet(out / 'ldap_monthly_context.parquet', index=False, compression='zstd')
    aggregates, pcs, hours, coverage, quality, zero_cols = [], [], [], [], {}, []
    for source in SOURCES:
        daily, pc, hour, cov, qc, counts = aggregate_source(root, source, ldap, args)
        aggregates.append(daily)
        pcs.append(pc)
        hours.append(hour)
        coverage.append(cov)
        quality[source] = qc
        zero_cols.extend(counts)
        gc.collect()
    observed = pd.concat(aggregates, axis=1)
    first, last = observed.index.get_level_values('date').min(), observed.index.get_level_values('date').max()
    all_dates = pd.date_range(first, last, freq='D')
    # Calendar rows only for monthly-roster users; preserve any observed out-of-roster row.
    calendar = pd.DataFrame({'date': all_dates})
    calendar['snapshot_month'] = calendar.date.dt.strftime('%Y-%m')
    missing_months = set(calendar.snapshot_month) - set(ldap.snapshot_month)
    if missing_months:
        raise ValueError(f'Missing LDAP snapshots: {missing_months}; do not silently forward-fill')
    roster = calendar.merge(ldap[['user', 'snapshot_month']], on='snapshot_month')[KEY]
    keys = pd.concat([roster, observed.reset_index()[KEY]]).drop_duplicates(KEY)
    daily = keys.merge(observed.reset_index(), on=KEY, how='left', validate='one_to_one')
    daily[zero_cols] = daily[zero_cols].fillna(0).astype('int64')
    all_pc = pd.concat(pcs).drop_duplicates(KEY + ['pc'])
    all_hour = pd.concat(hours).drop_duplicates(KEY + ['hour'])
    unique_pc = all_pc.groupby(KEY).pc.nunique().rename('all_pc_count')
    unique_hour = all_hour.groupby(KEY).hour.nunique().rename('active_hour_count')
    first_pc = all_pc.groupby(['user', 'pc']).date.min().reset_index().groupby(KEY).size().rename('new_pc_count')
    for feature in [unique_pc, unique_hour, first_pc]:
        daily = daily.merge(feature, on=KEY, how='left', validate='one_to_one')
        daily[feature.name] = daily[feature.name].fillna(0).astype('int64')
    daily['total_event_count'] = daily[[s + '_event_count' for s in SOURCES]].sum(axis=1)
    daily['after_hours_event_count'] = daily[[s + '_after_hours_count' for s in SOURCES]].sum(axis=1)
    daily['after_hours_event_ratio'] = daily.after_hours_event_count / daily.total_event_count.replace(0, np.nan)
    daily['first_event_minute'] = daily[[s + '_first_minute' for s in SOURCES]].min(axis=1)
    daily['last_event_minute'] = daily[[s + '_last_minute' for s in SOURCES]].max(axis=1)
    daily['observed_span_minutes'] = daily.last_event_minute - daily.first_event_minute
    daily['has_activity'] = daily.total_event_count.gt(0)
    daily['no_observed_activity'] = ~daily.has_activity
    daily['weekday'] = daily.date.dt.dayofweek
    daily['is_weekend'] = daily.weekday.ge(5)
    daily['day_type'] = np.where(daily.is_weekend, 'weekend', 'weekday')
    daily['snapshot_month'] = daily.date.dt.strftime('%Y-%m')
    daily = daily.merge(ldap, on=['user', 'snapshot_month'], how='left', validate='many_to_one', indicator=True)
    daily['ldap_present'] = daily.pop('_merge').eq('both')
    cov = pd.concat(coverage, axis=1).reindex(all_dates).fillna(0).astype('int64')
    cov.index.name = 'date'
    for source in SOURCES:
        start = pd.Timestamp(quality[source]['min_timestamp']).normalize()
        end = pd.Timestamp(quality[source]['max_timestamp']).normalize()
        cov[source + '_day_status'] = np.select(
            [(cov.index < start) | (cov.index > end), (cov.index == start) | (cov.index == end),
             cov[source + '_raw_event_count'].eq(0)],
            ['outside_observed_range', 'boundary_day', 'no_global_events'], default='interior_observed')
    cov['all_sources_observed_interior'] = cov[[s + '_day_status' for s in SOURCES]].eq('interior_observed').all(axis=1)
    daily = daily.merge(cov[['all_sources_observed_interior']], on='date', how='left', validate='many_to_one')
    daily['baseline_eligible'] = daily.ldap_present & daily.all_sources_observed_interior
    daily = daily.sort_values(KEY).reset_index(drop=True)
    assert not daily.duplicated(KEY).any()
    assert int(daily.total_event_count.sum()) == sum(q['rows'] for q in quality.values())
    assert daily.loc[~daily.has_activity, 'first_event_minute'].isna().all()
    assert (daily.loc[daily.has_activity, 'last_event_minute'] >= daily.loc[daily.has_activity, 'first_event_minute']).all()
    assert int(daily.email_size_sum.sum()) == quality['email']['numeric_totals']['size']
    assert int(daily.email_attachment_count.sum()) == quality['email']['numeric_totals']['attachments']
    cov.to_csv(out / 'source_day_coverage.csv', encoding='utf-8-sig')
    daily.to_parquet(out / 'daily_features.parquet', index=False, compression='zstd')
    daily.to_csv(out / 'daily_features.csv', index=False, encoding='utf-8-sig', float_format='%.6f')
    daily.head(200).to_csv(out / 'daily_features_preview.csv', index=False, encoding='utf-8-sig')
    feature_dictionary(daily).to_csv(out / 'feature_dictionary.csv', index=False, encoding='utf-8-sig')
    log(f'Daily table: {len(daily):,} rows, {daily.user.nunique():,} users, {len(daily.columns)} columns')
    del aggregates, pcs, hours, all_pc, all_hour, observed
    gc.collect()
    rolling_info = write_rolling(daily, out, args)
    # Descriptive only: entire period, unsuitable for retrospective anomaly scoring.
    profile = daily.loc[daily.baseline_eligible].groupby(['user', 'day_type'])[FEATURES].agg(['count', 'mean', 'std', 'median'])
    profile.columns = [f'{feature}__{stat}' for feature, stat in profile.columns]
    profile.reset_index().to_csv(out / 'user_profile_full_period_descriptive_only.csv', index=False, encoding='utf-8-sig')
    summary = dict(date_min=str(first.date()), date_max=str(last.date()), calendar_days=len(all_dates),
                   users=daily.user.nunique(), user_days=len(daily), columns=len(daily.columns),
                   observed_user_days=int(daily.has_activity.sum()), zero_activity_user_days=int((~daily.has_activity).sum()),
                   ldap_absent_observed_user_days=int((~daily.ldap_present & daily.has_activity).sum()),
                   baseline_eligible_user_days=int(daily.baseline_eligible.sum()),
                   excluded_source_dates=[str(x.date()) for x in cov.index[~cov.all_sources_observed_interior]],
                   total_raw_events=sum(q['rows'] for q in quality.values()), source_quality=quality,
                   rolling=rolling_info, elapsed_seconds=round(perf_counter() - started, 1))
    write_json(out / 'quality_report.json', summary)
    config = vars(args).copy()
    config.update(features=FEATURES, timestamp_timezone='unspecified; original clock retained',
                  ldap_effective_time_assumption='snapshot applies to the named calendar month',
                  baseline_interval='[date - window_days, date), same user and weekday/weekend',
                  zeros='No observed events, not proof of inactivity or collection completeness',
                  source_files=[dict(path=str(root / f'{s}.csv'), bytes=(root / f'{s}.csv').stat().st_size,
                                     mtime_ns=(root / f'{s}.csv').stat().st_mtime_ns) for s in SOURCES])
    write_json(out / 'config.json', config)
    write_report(out, summary, args)
    log(json.dumps({k: v for k, v in summary.items() if k != 'source_quality'}, ensure_ascii=False, default=str))


def write_report(out, q, args):
    source_rows = '\n'.join(f'| {s}.csv | {v["rows"]:,} | {v["users"]:,} |' for s, v in q['source_quality'].items())
    report = f'''# 사용자 × 일 행동 로그 baseline

## 산출 결과

- 기간: **{q['date_min']} ~ {q['date_max']}**, {q['calendar_days']:,}일
- 사용자: **{q['users']:,}명**, 사용자·날짜 행: **{q['user_days']:,}개**, 컬럼: {q['columns']}개
- 로그 관찰 행: {q['observed_user_days']:,}; 로그 미관찰 행: {q['zero_activity_user_days']:,}
- 원본 5종 이벤트 총계: **{q['total_raw_events']:,}건**. 일별 집계 합계와 일치 검증.
- 과거 기준에 포함 가능한 사용자·날짜: {q['baseline_eligible_user_days']:,}
- 최소 이력을 확보한 기준 행: {q['rolling']['ready_rows']:,}; 당일도 기준 적격인 행: {q['rolling']['ready_and_eligible_rows']:,}
- 월별 LDAP에 없는 관찰 사용자·날짜: {q['ldap_absent_observed_user_days']:,} (행 보존, 기준 학습 제외)

| 원본 | 이벤트 수 | 사용자 수 |
|---|---:|---:|
{source_rows}

## 파일 선택

1. `daily_features.parquet` / `daily_features.csv`: **user + date가 유일한 키**인 일별 행동 테이블. 두 파일의 의미는 동일하며 파이썬에서는 자료형이 보존되는 Parquet 권장.
2. `rolling_baseline.parquet`: 동일 키의 과거 전용 개인 기준. {len(FEATURES)}개 지표 각각에 `__n`, `__mean`, `__std`, `__median`, `__q25`, `__q75`, `__p95` 제공. float32로 저장하며 n은 정수값. 당일 실제값은 daily_features에 있음.
3. `user_profile_full_period_descriptive_only.csv`: 전체 기간 개인별 평일/주말 요약. **미래 정보가 포함되므로 과거 날짜의 이상치 판정에는 사용 금지**.
4. `feature_dictionary.csv`: 모든 일별 컬럼 정의, 결측 수, rolling 포함 여부.
5. `source_day_coverage.csv`, `quality_report.json`, `config.json`: 소스별 날짜 범위, 검증 결과, 재실행 설정.
6. `ldap_monthly_context.parquet`: 월별 조직 속성; `psychometric_context_only.csv`: 별도 심리측정 원본 속성. 성격 점수로 이상행동을 판단하지 않음.

## 기본 기준

- 날짜 t의 기준은 **[t−{args.window_days}일, t)** 범위에서 같은 사용자·같은 평일/주말 구분만 사용. 당일 값과 미래 날짜를 제외.
- 평일 최소 {args.min_weekday}개, 주말 최소 {args.min_weekend}개 과거 적격 관측치 필요. 미달이면 통계는 결측으로 유지. `__n`으로 지표별 실제 표본 수 확인.
- 표준편차는 표본 표준편차(ddof=1), 분위수는 선형 보간으로 계산.
- `baseline_ready`는 전체 이벤트 수의 이력이 충분한지 나타냄. 이메일 평균 크기/첫·마지막 활동 시각처럼 무활동일에 결측인 지표는 해당 `__n`을 별도로 확인해야 함.
- 과거 적격일 중 **로그 없는 날의 건수 0은 기준에 포함**. 시간·비율·평균처럼 분모/이벤트가 없는 값은 결측. 소스 경계일·전역 미관찰일·LDAP 미등록일은 학습에서 제외.
- 시간 외 활동은 원본 시각 기준 **{args.work_start:02d}:00 이상 ~ {args.work_end:02d}:00 미만 구간 밖**. 근무표가 없는 상태의 설정값이며 비정상 확정 기준이 아님. 주말 여부와 독립적으로 계산. 공휴일 미반영.
- 외부 수신자 주소는 도메인이 {', '.join(args.internal_domains)}에 정확히 일치하지 않는 경우. to/cc/bcc를 모두 확인하고 한 이벤트 안의 중복 주소 제거.
- 웹 호스트/PC 신규성은 과거 날짜와 비교. 첫 관찰일의 자원은 모두 신규이며 당일 반복 사용은 신규 개수를 증가시키지 않음.

## 해석 및 시간 정보 제한

- 이 결과는 **관찰 행동 기준**이며 정상 데이터만으로 검증된 기준은 아님. answers/ 및 악성 라벨은 읽거나 결합하지 않음. 과거에 포함된 이상행동이 이동 기준을 오염시킬 수 있음.
- LDAP 파일명에 표시된 월에 해당 명단이 유효하다고 가정. 스냅샷의 실제 수집/배포 시각이 없으므로 엄밀한 운영 시점 가용성은 확인 불가. 확정적인 일별 입퇴사일로 해석하지 않음.
- 월별 명단 사용자 날짜 + 실제 로그 관찰 날짜를 사용. 명단에서 빠진 이후의 날짜를 전부 0으로 만들지 않음.
- 첫/마지막 로그 날짜는 하루 전체 수집 여부가 불명확해 보수적으로 학습에서 제외: {', '.join(q['excluded_source_dates'])}. 각 소스의 양 끝 날짜 및 전역 이벤트가 없는 날짜가 대상. 그 외 날짜도 완전 수집이 보증되지는 않음.
- 이메일 user와 from은 다를 수 있어 전체 이메일을 발송 수로 취급하지 않음. LDAP 발신 주소 일치 + 외부 수신 주소는 별도 보조 지표이며, 발송·유출이 검증된 정답이 아님.
- file에는 작업 종류·전송량이 없어 복사/유출 건수로 이름 붙이지 않음. HTTP는 접근 로그이며 업로드 여부·전송량을 알 수 없음. device 연결을 전송 완료로 취급하지 않음.
- 표준편차/IQR이 0인 희소 지표에 작은 상수를 더해 큰 z-score를 만들지 말 것. `이전 값이 항상 0이었는데 처음 발생` 같은 상태를 별도로 처리.
- p95 초과는 참고 기준이며 악성 확정/최종 경보 임계값이 아님. 지표 다중 비교, 업무·조직 변경, 연속 이상일로 인한 기준 오염을 이후 평가에서 고려.
- 첫/마지막 시각은 자정 기준 분으로 표현. 자정 전후 근무를 분석할 때 선형 z-score 대신 순환 시각이나 별도 근무일 정의 검토.

## 파이썬 사용 예

```python
import pandas as pd
from pathlib import Path

path = Path("outputs/legacy/user_day_baseline_20260916")
daily = pd.read_parquet(path / "daily_features.parquet")
metric = "email_ldap_sender_external_event_count"
base = pd.read_parquet(path / "rolling_baseline.parquet", columns=[
    "user", "date", "baseline_ready", "minimum_history_days",
    metric + "__n", metric + "__mean", metric + "__std", metric + "__p95"
])
review = daily[["user", "date", "baseline_eligible", metric]].merge(
    base, on=["user", "date"], validate="one_to_one"
)
eligible = review.baseline_eligible & (review[metric + "__n"] >= review.minimum_history_days)
review["above_personal_p95"] = eligible & (review[metric] > review[metric + "__p95"])
# 단순 참고 신호이며 악성/유출 판정이 아님.
```

재생성: `python src/pipelines/user_day_baseline/build_baseline.py`

필수 패키지: pandas, numpy, pyarrow. 기본값 및 옵션은 `--help` 참고.
'''
    (out / 'README_ko.md').write_text(report, encoding='utf-8')


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=PROJECT_ROOT / 'inputs/events')
    parser.add_argument('--output-dir', type=Path, default=PROJECT_ROOT / "outputs/legacy/user_day_baseline_20260916")
    parser.add_argument('--window-days', type=int, default=60)
    parser.add_argument('--min-weekday', type=int, default=20)
    parser.add_argument('--min-weekend', type=int, default=8)
    parser.add_argument('--work-start', type=int, default=8)
    parser.add_argument('--work-end', type=int, default=18)
    parser.add_argument('--internal-domains', nargs='+', default=['dtaa.com'])
    args = parser.parse_args()
    if not 0 <= args.work_start < args.work_end <= 24:
        parser.error('Work hours must satisfy 0 <= start < end <= 24')
    if min(args.window_days, args.min_weekday, args.min_weekend) < 1:
        parser.error('Window and minimum history must be positive')
    args.internal_domains = [x.lower() for x in args.internal_domains]
    return args


if __name__ == '__main__':
    build(parse_args())
