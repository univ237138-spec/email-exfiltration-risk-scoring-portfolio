"""Read-only checks for the overview dashboard: plan acceptance numbers and every page rendering."""
from pathlib import Path
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

import services as sv

HERE = Path(__file__).resolve().parent


def _page(view, start, end, user=None, date=None):
    """Render one view with a given period, bypassing navigation."""
    def script(view, start, end, user, date, here):
        import importlib
        import sys
        sys.path.insert(0, here)
        import pandas as pd
        import streamlit as st
        import services as sv
        import ui
        ui.PAGES.update({k: st.Page(lambda: None, title=k, url_path=k) for k in ("overview", "ranking", "detail", "policy")})
        data, meta, prov = ui.snapshot(sv.signature())
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        scope = sv.filter_scope(data, s, e)
        st.session_state["_ctx"] = ui.Context(data, meta, prov, s, e, "전체", "전체", "", scope, None, None)
        if user:
            st.session_state.setdefault("sel_user", user)
            st.session_state.setdefault("sel_date", pd.Timestamp(date))
        importlib.import_module(f"views.{view}").render()
    at = AppTest.from_function(script, args=(view, start, end, user, date, str(HERE)), default_timeout=180)
    return at.run()


class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = sv.signature()
        cls.data, cls.meta, _ = sv.load_snapshot()

    @classmethod
    def tearDownClass(cls):
        assert cls.before == sv.signature(), "confirmed outputs changed during checks"

    def test_plan_numbers(self):
        self.assertEqual(len(self.data), 330452)
        post = sv.filter_scope(self.data, "2010-06-01", "2011-05-17")
        s = sv.summary(post)
        self.assertEqual((s["users"], s["scored"], s["review_users"], s["alerts"]), (975, 225281, 340, 842))
        self.assertEqual(int(post.total_score.ge(3).sum()), 498)
        self.assertEqual(int(post.logon_alert.sum()), 344)
        ranking = sv.user_ranking(post)
        self.assertEqual(len(ranking), 340)
        self.assertEqual(int(ranking.alert_days.sum()), post[post.review_target].groupby("user").date.nunique().sum())
        dist = sv.user_grade_distribution(post)
        self.assertEqual(dist["위험"] + dist["주의"], 340)
        self.assertEqual(sum(dist[g] for g in sv.GRADE_ORDER), 975)

    def test_case_xhw0498(self):
        row = self.data[self.data.user.eq("XHW0498") & self.data.date.eq("2010-08-20")].iloc[0]
        self.assertEqual((int(row.total_score), row.risk_grade, int(row.logon_score), row.logon_grade), (5, "위험", 0, "정상"))
        scope = sv.filter_scope(self.data, "2010-08-01", "2010-09-30")
        alerts = scope[scope.user.eq("XHW0498") & scope.review_target]
        self.assertTrue({"2010-09-09", "2010-09-28"} <= set(alerts.date.dt.strftime("%Y-%m-%d")))
        self.assertIn("이메일 위험", sv.reason_sentence(row))

    def test_views_render(self):
        for view in ("overview", "ranking", "detail", "policy"):
            at = _page(view, "2010-08-01", "2010-09-30", "XHW0498", "2010-08-20")
            self.assertFalse(at.exception, f"{view}: {[e.value for e in at.exception]}")
        at = _page("detail", "2010-08-01", "2010-09-30", "XHW0498", "2010-08-20")
        text = " ".join(m.value for m in at.markdown)
        self.assertIn("XHW0498", text)
        self.assertIn("이메일 위험", text)

    def test_empty_scope(self):
        at = _page("overview", "2010-01-02", "2010-01-03")
        self.assertFalse(at.exception)


if __name__ == "__main__":
    unittest.main(verbosity=2)
