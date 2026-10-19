"""Tests for the orchestrator's own logic, with a fake AI provider (no network or database)."""

from analysis.abstract_provider import AbstractProvider
from orchestrator import Orchestrator
from shared.score_priority import compute_scores


class FakeProvider(AbstractProvider):
    """A provider that is never asked for an analysis; only its fingerprint is used."""

    model = "fake-model"


def test_prepare_contractor_rounds_then_adds_scores_and_fingerprint():
    """GAF's raw numbers are rounded to the stored format first, then scored and fingerprinted from those values."""
    contractor = {
        "gaf_id": "42", "name": "Example Roofing", "rating": 4.6666, "review_count": 120,
        "certification": "Master Elite", "president_club_stars": 1, "commercial_certification": None,
        "services": ["Metal"], "address": "1 Main St Newark, NJ 07101", "distance_miles": 9.876,
    }
    provider = FakeProvider()
    Orchestrator(provider)._helper_prepare_contractor(contractor)
    assert contractor["rating"] == 4.7
    assert contractor["distance_miles"] == 9.88
    rounded = dict(contractor, rating=4.7, distance_miles=9.88)
    for name, value in compute_scores(rounded).items():
        assert contractor[name] == value
    assert contractor["fingerprint"] == provider.compute_fingerprint(rounded)
