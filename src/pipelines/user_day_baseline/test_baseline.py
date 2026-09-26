"""Behavioral tests for temporal leakage, missingness and calendar windows."""
import unittest

import numpy as np
import pandas as pd

from build_baseline import recipient_addresses, rolling_one_user


class BaselineTests(unittest.TestCase):
    def frame(self, dates, values, eligible=None):
        dates = pd.to_datetime(dates)
        return pd.DataFrame({
            'user': 'TEST', 'date': dates, 'x': values,
            'day_type': np.where(dates.dayofweek >= 5, 'weekend', 'weekday'),
            'baseline_eligible': eligible if eligible is not None else True,
        })

    def calculate(self, frame, window=60, minimum=1):
        return rolling_one_user(frame, ['x'], window, minimum, minimum).set_index('date')

    def test_current_and_future_values_never_affect_current_baseline(self):
        frame = self.frame(['2020-01-06', '2020-01-07', '2020-01-08', '2020-01-09'], [2, 4, 6, 8])
        expected = self.calculate(frame).loc['2020-01-08']
        frame.loc[frame.date >= '2020-01-08', 'x'] = 100000
        actual = self.calculate(frame).loc['2020-01-08']
        self.assertEqual(actual['x__mean'], 3)
        for stat in ['n', 'mean', 'std', 'median', 'q25', 'q75', 'p95']:
            self.assertEqual(actual['x__' + stat], expected['x__' + stat])

    def test_window_is_calendar_days_and_left_boundary_inclusive(self):
        frame = self.frame(['2020-01-01', '2020-01-02', '2020-03-02'], [999, 7, 888])
        result = self.calculate(frame).loc['2020-03-02']
        self.assertEqual(result['x__n'], 1)
        self.assertEqual(result['x__mean'], 7)

    def test_weekends_and_weekdays_are_separate(self):
        frame = self.frame(['2020-01-03', '2020-01-04', '2020-01-05', '2020-01-06'], [5, 100, 200, 9])
        result = self.calculate(frame)
        self.assertEqual(result.loc['2020-01-05', 'x__mean'], 100)
        self.assertEqual(result.loc['2020-01-06', 'x__mean'], 5)

    def test_zero_activity_is_retained_and_ineligible_days_excluded(self):
        frame = self.frame(['2020-01-06', '2020-01-07', '2020-01-08', '2020-01-09'],
                           [0, 1000, 4, 2], [True, False, True, True])
        result = self.calculate(frame).loc['2020-01-09']
        self.assertEqual(result['x__n'], 2)
        self.assertEqual(result['x__mean'], 2)

    def test_cold_start_is_missing_and_constant_variance_stays_zero(self):
        frame = self.frame(pd.date_range('2020-01-06', periods=4), [0, 0, 0, 10])
        result = self.calculate(frame, minimum=2)
        self.assertTrue(np.isnan(result.iloc[1]['x__mean']))
        self.assertFalse(result.iloc[1]['baseline_ready'])
        self.assertEqual(result.iloc[3]['x__std'], 0)
        self.assertEqual(result.iloc[3]['x__p95'], 0)

    def test_feature_specific_missing_values_do_not_become_zero(self):
        frame = self.frame(pd.date_range('2020-01-06', periods=4), [2, np.nan, 4, 8])
        result = self.calculate(frame, minimum=2).iloc[-1]
        self.assertEqual(result['x__n'], 2)
        self.assertEqual(result['x__mean'], 3)

    def test_recipient_deduplication_across_to_cc_bcc(self):
        self.assertEqual(recipient_addresses([' A@dtaa.com;b@outside.com', 'a@DTAA.com;', '']),
                         ['a@dtaa.com', 'b@outside.com'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
