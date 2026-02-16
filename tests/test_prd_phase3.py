"""Phase 3 PRD gap-closure tests — F05 + F06."""
import pytest
import os


class TestNewsRSSSources:
    """F05-A: News RSS must have all 7+ sources."""

    def test_news_feeds_count_at_least_seven(self):
        from api.intelligence.scraper_news import NEWS_FEEDS
        assert len(NEWS_FEEDS) >= 7

    def test_news_feeds_has_tyee(self):
        from api.intelligence.scraper_news import NEWS_FEEDS
        names = [f["name"].lower() for f in NEWS_FEEDS]
        assert any("tyee" in n for n in names)

    def test_news_feeds_has_storeys(self):
        from api.intelligence.scraper_news import NEWS_FEEDS
        names = [f["name"].lower() for f in NEWS_FEEDS]
        assert any("storeys" in n or "storey" in n for n in names)

    def test_news_feeds_has_western_investor(self):
        from api.intelligence.scraper_news import NEWS_FEEDS
        names = [f["name"].lower() for f in NEWS_FEEDS]
        assert any("western investor" in n for n in names)


class TestSchedulerIntegration:
    """F05-A + F06-A: Scheduler must register risk and undervalued jobs."""

    def test_scheduler_has_political_risk_schedule(self):
        import inspect
        from api.intelligence.scheduler import ScraperScheduler
        source = inspect.getsource(ScraperScheduler._register_defaults)
        assert "political_risk" in source

    def test_scheduler_political_risk_monthly(self):
        import inspect
        from api.intelligence.scheduler import ScraperScheduler
        source = inspect.getsource(ScraperScheduler._register_defaults)
        assert "0 2 1 * *" in source

    def test_scheduler_has_undervalued_schedule(self):
        import inspect
        from api.intelligence.scheduler import ScraperScheduler
        source = inspect.getsource(ScraperScheduler._register_defaults)
        assert "undervalued" in source

    def test_scheduler_undervalued_weekly(self):
        import inspect
        from api.intelligence.scheduler import ScraperScheduler
        source = inspect.getsource(ScraperScheduler._register_defaults)
        assert "0 15 * * 1" in source


class TestK8sCronJobs:
    """F05-B + F06-A: K8s CronJobs must exist."""

    def test_political_risk_cronjob_exists(self):
        assert os.path.isfile("k8s/cronjob-political-risk.yaml")

    def test_political_risk_cronjob_has_monthly_schedule(self):
        with open("k8s/cronjob-political-risk.yaml") as f:
            content = f.read()
        assert "0 2 1 * *" in content

    def test_political_risk_cronjob_calls_materialize(self):
        with open("k8s/cronjob-political-risk.yaml") as f:
            content = f.read()
        assert "political_risk" in content or "materialize" in content

    def test_undervalued_cronjob_exists(self):
        assert os.path.isfile("k8s/cronjob-undervalued.yaml")

    def test_undervalued_cronjob_has_weekly_schedule(self):
        with open("k8s/cronjob-undervalued.yaml") as f:
            content = f.read()
        assert "0 15 * * 1" in content

    def test_undervalued_cronjob_calls_score(self):
        with open("k8s/cronjob-undervalued.yaml") as f:
            content = f.read()
        assert "undervalued" in content or "score_parcels" in content
