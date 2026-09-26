"""Shared feature/model helpers for the channel-wise Isolation Forest comparison. Never reads labels."""
from pathlib import Path
PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "PROJECT_STRUCTURE.md").is_file())
import sys
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))
from scoring import VERSION, Policy, CORE, LOGON  # noqa: E402

EMAIL_Z = [c + '_z' for c in CORE]
LOGON_Z = [c + '_z' for c in LOGON]
CHANNELS = {'email': EMAIL_Z + ['jobkw_mail_flag', 'novel_night_mail'], 'logon': LOGON_Z}
CAL_START, CAL_END = '2010-01-01', '2010-05-31'
TUNE_TRAIN_END = '2010-04-30'
FROZEN = OUT / 'frozen_if_calibration.json'


def load():
    meta = json.loads((PROJECT_ROOT / "outputs/dashboard/metadata.json").read_text(encoding='utf-8'))
    assert meta['source']['version'] == VERSION and meta['policy'] == Policy().to_dict()
    d = pd.read_parquet(PROJECT_ROOT / "outputs/dashboard/scored.parquet")
    d = d.loc[d.is_scored.eq(1)].reset_index(drop=True)
    assert len(d) == meta['scored_rows'] and not d.duplicated(['user', 'date']).any()
    d['novel_night_mail'] = (d.night_mail_flag.eq(1) & d.night_mail_past30.eq(0)).astype(int)
    d['cur_email'] = d.total_score.ge(Policy().caution)
    d['cur_logon'] = d.logon_alert.astype(bool)
    d['cur_review'] = d.review_target.astype(bool)
    assert (d.cur_email | d.cur_logon).eq(d.cur_review).all()
    d['cal'] = d.date.between(CAL_START, CAL_END)
    return d


def features(d, channel, clip=True):
    x = d[CHANNELS[channel]].to_numpy(dtype=float)
    assert np.isfinite(x).all()
    if clip:  # keep only increases over the personal baseline; flags are already 0/1
        x = np.maximum(x, 0.0)
    return x


def fit(x, n_estimators, max_samples, seed):
    return IsolationForest(n_estimators=n_estimators, max_samples=min(max_samples, len(x)), max_features=1.0,
                           bootstrap=False, random_state=seed, n_jobs=-1).fit(x)


def anomaly(model, x):
    """Higher = more anomalous."""
    return -model.score_samples(x)


def threshold(train_scores, rate):
    return float(np.quantile(train_scores, 1 - rate, method='higher'))
