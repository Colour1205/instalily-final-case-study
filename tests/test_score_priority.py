"""Tests for the shared priority score formula (no network or database)."""

import pytest

from shared.score_priority import compute_scores


def make_contractor(**overrides) -> dict:
    """A made-up contractor row; keyword arguments replace the defaults."""
    contractor = {
        "gaf_id": "1", "name": "Example Roofing", "rating": 5.0, "review_count": 100,
        "certification": "Master Elite", "president_club_stars": 1, "commercial_certification": None,
        "services": ["Metal", "Solar"], "address": "1 Main St Newark, NJ 07101", "distance_miles": 25.0,
    }
    contractor.update(overrides)
    return contractor


def part(name: str, **overrides) -> float:
    """One part of the score for a contractor with the given changes."""
    return compute_scores(make_contractor(**overrides))[name]


def test_scores_match_hand_worked_example():
    """5.0 from 100 reviews, Master Elite with 1 star, 2 lines, 25 miles; every value rounded to 2 decimals."""
    scores = compute_scores(make_contractor())
    assert scores["review_count_adjust_rating"] == 12.5
    assert scores["gaf_rank"] == 20
    assert scores["specialty"] == 16.67
    assert scores["distance"] == 12.5
    assert scores["priority_score"] == 61.67


def test_review_count_adjust_rating():
    """No reviews and low ratings get 0; many good reviews beat a few perfect ones."""
    assert part("review_count_adjust_rating", rating=None, review_count=0) == 0
    assert part("review_count_adjust_rating", rating=3.3, review_count=50) == 0
    few_perfect = part("review_count_adjust_rating", rating=5.0, review_count=8)
    many_good = part("review_count_adjust_rating", rating=4.9, review_count=1330)
    assert many_good > few_perfect


def test_gaf_rank_combines_certification_and_presidents_club():
    """Certification gives 0/5/10, President's Club adds 10/15, capped at 25."""
    assert part("gaf_rank", certification="Certified", president_club_stars=0) == 0
    assert part("gaf_rank", certification="Certified Plus", president_club_stars=0) == 5
    assert part("gaf_rank", certification="Master Elite", president_club_stars=0) == 10
    assert part("gaf_rank", certification="Master Elite", president_club_stars=1) == 20
    assert part("gaf_rank", certification="Master Elite", president_club_stars=2) == 25
    assert part("gaf_rank", certification="Master Elite", president_club_stars=3) == 25


def test_specialty_and_distance():
    """Specialty is full at 3 lines; distance never reaches zero."""
    assert part("specialty", services=[]) == 0
    assert part("specialty", services=["Metal", "Solar", "Coatings", "Asphaltic"]) == pytest.approx(25)
    assert part("distance", distance_miles=0) == 25
    assert 0 < part("distance", distance_miles=1000) < 1
