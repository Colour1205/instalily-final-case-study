"""Tests for GAFScraper's fetching and parsing, using made-up data (no network or database)."""

import time

import httpx

from scraping.scraper_gaf import GAFScraper

scraper = GAFScraper("10013")


class FakeResponse:
    """Stands in for an httpx response."""

    def __init__(self, status_code: int, data: dict) -> None:
        """Remember the status code and JSON body to return."""
        self.status_code = status_code
        self.data = data

    def raise_for_status(self) -> None:
        """Do nothing, like a successful response."""

    def json(self) -> dict:
        """Return the prepared JSON body."""
        return self.data


def test_parse_result_reads_search_fields():
    """A full made-up search result becomes the right contractor row."""
    result = {
        "uri": "https://example.com/profile/42",
        "raw": {
            "gaf_contractor_id": "42",
            "gaf_navigation_title": "Example Roofing",
            "gaf_rating": 4.7,
            "gaf_number_of_reviews": 12,
            "gaf_address": "1 Main St Newark, NJ 07101",
            "distanceinmiles": 9.876,
            "gaf_latitude": 40.7,
            "gaf_longitude": -74.1,
            "gaf_featured_image_src": "https://services.gaf.com/photo.jpg?width=120",
            "gaf_residential_presidents_club_stars_count": 2,
            "gaf_f_contractor_certifications_and_awards_residential": [
                "President's Club - Award", "GAF Master Elite® - Certification",
            ],
            "gaf_f_contractor_designations_residential": ["MASTER_ELITE^_^RESIDENTIAL^_^C", "METAL^_^RESIDENTIAL^_^T"],
            "gaf_f_contractor_designations_commercial": ["GOLDELITE^_^COMMERCIAL^_^C"],
            "gaf_f_contractor_technologies_commercial": ["Single-Ply Roofer"],
        },
    }
    contractor = scraper.parse_result(result)
    assert contractor["gaf_id"] == "42"
    assert contractor["rating"] == 4.7
    assert contractor["certification"] == "Master Elite"
    assert contractor["president_club_stars"] == 2
    assert contractor["commercial_certification"] == "GoldElite"
    assert contractor["services"] == ["Metal", "Single-Ply"]
    assert contractor["distance_miles"] == 9.88
    assert contractor["address"] == "1 Main St Newark, NJ 07101"
    assert contractor["latitude"] == 40.7
    assert contractor["longitude"] == -74.1
    assert contractor["logo_url"] == "https://services.gaf.com/photo.jpg?width=120"


def test_parse_result_handles_sparse_contractor():
    """No reviews means no rating, and single values are read like lists."""
    result = {
        "raw": {
            "gaf_contractor_id": 7,
            "gaf_rating": 0.0,
            "gaf_number_of_reviews": 0,
            "gaf_f_contractor_certifications_and_awards_residential": "GAF Certified Plus™ - Certification",
            "gaf_featured_image_src": "/-/media/images/no_profile_image.svg",
        },
    }
    contractor = scraper.parse_result(result)
    assert contractor["rating"] is None
    assert contractor["certification"] == "Certified Plus"
    assert contractor["services"] == []
    assert contractor["distance_miles"] is None
    assert contractor["logo_url"] is None


def test_fetch_retries_then_skips_broken_results(monkeypatch):
    """A 503 is retried; results with no id or no name are skipped; the rest are scored."""
    results = [
        {"raw": {"gaf_contractor_id": "1", "gaf_navigation_title": "Good Roofing", "distanceinmiles": 3.0}},
        {"raw": {"gaf_contractor_id": "2", "distanceinmiles": 4.0}},
        {"raw": {"gaf_navigation_title": "Mystery Roofing"}},
    ]
    responses = [FakeResponse(503, {}), FakeResponse(200, {"totalCount": 3, "results": results})]

    def fake_post(*args, **kwargs):
        """Return the prepared responses in order."""
        return responses.pop(0)

    def fake_sleep(seconds):
        """Skip the real wait between retries."""

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(time, "sleep", fake_sleep)
    contractors = scraper.fetch()
    assert len(contractors) == 1
    assert contractors[0]["gaf_id"] == "1"
    assert contractors[0]["priority_score"] > 0
    parts = contractors[0]["review_count_adjust_rating"] + contractors[0]["gaf_rank"]
    parts += contractors[0]["specialty"] + contractors[0]["distance"]
    assert abs(parts - contractors[0]["priority_score"]) < 0.05
