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


class TestUndervaluedWatchlistRules:
    """F06-B: Undervalued alert filter rule types."""

    def test_rule_type_has_undervalued_discount(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "UNDERVALUED_DISCOUNT")

    def test_rule_type_has_undervalued_lot_area(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "UNDERVALUED_LOT_AREA")

    def test_rule_type_has_undervalued_tod_tier(self):
        from api.intelligence.alerts import RuleType
        assert hasattr(RuleType, "UNDERVALUED_TOD_TIER")

    def test_match_undervalued_discount_above_threshold(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"discount_pct": 25.0}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_DISCOUNT, rule_value="20")
        assert AlertEngine.match_rule(signal, rule) is True

    def test_match_undervalued_discount_below_threshold(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"discount_pct": 15.0}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_DISCOUNT, rule_value="20")
        assert AlertEngine.match_rule(signal, rule) is False

    def test_match_undervalued_lot_area_above_min(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"lot_area_sqft": 5000}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_LOT_AREA, rule_value="4000")
        assert AlertEngine.match_rule(signal, rule) is True

    def test_match_undervalued_lot_area_below_min(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"lot_area_sqft": 3000}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_LOT_AREA, rule_value="4000")
        assert AlertEngine.match_rule(signal, rule) is False

    def test_match_undervalued_tod_tier(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"tod_tier": 1}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_TOD_TIER, rule_value="1")
        assert AlertEngine.match_rule(signal, rule) is True

    def test_match_undervalued_tod_tier_no_match(self):
        from api.intelligence.alerts import AlertEngine, WatchlistRule, RuleType
        signal = {"tod_tier": 3}
        rule = WatchlistRule(rule_type=RuleType.UNDERVALUED_TOD_TIER, rule_value="1")
        assert AlertEngine.match_rule(signal, rule) is False


class TestRiskChoropleth:
    """F05-C: Map choropleth for neighborhood risk scores."""

    def test_political_risk_api_file_exists(self):
        assert os.path.isfile("frontend/src/lib/political-risk-api.ts")

    def test_political_risk_api_has_fetch_function(self):
        with open("frontend/src/lib/political-risk-api.ts") as f:
            content = f.read()
        assert "fetchNeighborhoodRiskScores" in content

    def test_mapview_has_risk_toggle(self):
        with open("frontend/src/components/MapView.tsx") as f:
            content = f.read()
        assert "showRisk" in content or "riskChoropleth" in content

    def test_mapview_has_risk_colors(self):
        with open("frontend/src/components/MapView.tsx") as f:
            content = f.read()
        # Should define risk score color thresholds
        assert ("RISK_COLORS" in content or "riskColor" in content or
                ("green" in content.lower() and "risk" in content.lower()))


class TestUndervaluedAlertGeneration:
    """F06-B: Alert generation after scoring run."""

    def test_generate_undervalued_alerts_exists(self):
        from api.intelligence import undervalued_scoring
        assert hasattr(undervalued_scoring, "generate_undervalued_alerts")

    def test_generate_undervalued_alerts_is_async(self):
        import asyncio
        from api.intelligence.undervalued_scoring import generate_undervalued_alerts
        assert asyncio.iscoroutinefunction(generate_undervalued_alerts)

    def test_score_parcels_references_alerts(self):
        import inspect
        from api.intelligence.undervalued_scoring import score_parcels
        source = inspect.getsource(score_parcels)
        assert "generate_undervalued_alerts" in source or "alert" in source.lower()
