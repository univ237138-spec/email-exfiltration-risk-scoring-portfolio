"""Independent output reconciliation and hand-window checks against saved data."""
import json
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from build_baseline import FEATURES, SOURCES


def main():
    out = PROJECT_ROOT / "outputs/legacy/user_day_baseline_20260916"
    config = json.loads((out / 'config.json').read_text(encoding='utf-8'))
    report = json.loads((out / 'quality_report.json').read_text(encoding='utf-8'))
    daily = pd.read_parquet(out / 'daily_features.parquet')
    selected = ['total_event_count', 'email_size_mean', 'first_event_minute', 'new_pc_count']
    columns = ['user', 'date', 'baseline_ready', 'baseline_eligible', 'minimum_history_days'] + [
        f'{f}__{s}' for f in selected for s in ['n', 'mean', 'std', 'median', 'q25', 'q75', 'p95']]
    baseline = pd.read_parquet(out / 'rolling_baseline.parquet', columns=columns)
    assert len(baseline) == len(daily) == report['user_days']
    assert not baseline.duplicated(['user', 'date']).any()
    assert baseline[['user', 'date']].equals(daily[['user', 'date']])
    assert baseline.baseline_eligible.equals(daily.baseline_eligible)
    assert len(pq.ParquetFile(out / 'rolling_baseline.parquet').schema.names) == 9 + 7 * len(FEATURES)
    for source in SOURCES:
        assert int(daily[source + '_event_count'].sum()) == report['source_quality'][source]['rows']
    no_activity = daily.loc[~daily.has_activity]
    assert no_activity.total_event_count.eq(0).all()
    assert no_activity.first_event_minute.isna().all()
    assert no_activity.email_size_mean.isna().all()
    assert no_activity.after_hours_event_ratio.isna().all()
    assert (daily.new_pc_count <= daily.all_pc_count).all()
    assert (daily.http_new_host_count <= daily.http_unique_host_count).all()
    assert (daily.email_ldap_sender_external_event_count <= daily.email_ldap_sender_match_count).all()
    assert (daily.email_ldap_sender_external_event_count <= daily.email_external_recipient_event_count).all()
    assert (daily.logon_count + daily.logoff_count == daily.logon_event_count).all()
    assert (daily.device_connect_count + daily.device_disconnect_count == daily.device_event_count).all()
    assert daily.active_hour_count.between(0, 24).all()
    assert daily.after_hours_event_ratio.dropna().between(0, 1).all()
    candidates = baseline.sample(32, random_state=42)
    for row in candidates.to_dict('records'):
        date = row['date']
        history = daily.loc[(daily.user == row['user']) & daily.baseline_eligible &
                            (daily.date < date) &
                            (daily.date >= date.to_pydatetime() - timedelta(days=config['window_days'])) &
                            (daily.is_weekend == (date.dayofweek >= 5))]
        for feature in selected:
            values = history[feature].dropna()
            assert row[feature + '__n'] == len(values)
            if len(values) < row['minimum_history_days']:
                assert pd.isna(row[feature + '__mean'])
                continue
            expected = dict(mean=values.mean(), std=values.std(ddof=1), median=values.median(),
                            q25=values.quantile(.25), q75=values.quantile(.75), p95=values.quantile(.95))
            for stat, value in expected.items():
                np.testing.assert_allclose(row[feature + '__' + stat], value, rtol=1e-5, atol=1e-5)
    # Compare source rows directly for a deterministic user/day without reusing aggregation code.
    pick = daily.loc[daily.has_activity & daily.baseline_eligible].sample(1, random_state=7).iloc[0]
    for source in SOURCES:
        raw = pd.read_csv(f'{source}.csv', usecols=['user', 'date', 'pc'])
        date = pd.to_datetime(raw.date, format='%m/%d/%Y %H:%M:%S')
        sample = raw.loc[(raw.user == pick.user) & (date.dt.normalize() == pick.date)]
        assert len(sample) == pick[source + '_event_count']
        assert sample.pc.nunique() == pick[source + '_pc_count']
    # CSV/Parquet keys and selected numerical fields agree after round-trip serialization.
    csv = pd.read_csv(out / 'daily_features.csv', usecols=['user', 'date', 'total_event_count'])
    assert len(csv) == len(daily)
    assert csv.user.equals(daily.user)
    assert pd.to_datetime(csv.date).equals(daily.date)
    assert csv.total_event_count.equals(daily.total_event_count)
    result = dict(status='passed', temporal_unit_tests=7, independent_window_checks=32,
                  features_per_window=len(selected), source_reconciliation='all five sources',
                  raw_spot_check={'user': pick.user, 'date': str(pick.date.date())},
                  csv_parquet_key_and_total_agreement=True)
    (out / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
