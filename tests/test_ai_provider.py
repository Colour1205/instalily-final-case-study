"""Tests for the AbstractAIProvider parent class, using a fake child provider (no real AI calls)."""

from decimal import Decimal

import pytest

from analysis.ai_provider import AbstractAIProvider


class FakeProvider(AbstractAIProvider):
    """A child provider that records the prompt and returns a prepared answer."""

    def __init__(self) -> None:
        """Start with no recorded prompts."""
        self.prompts = []
        self.system_prompts = []

    def _generate(self, system_prompt: str, user_prompt: str) -> dict:
        """Record the prompt and return a fixed answer."""
        self.prompts.append(user_prompt)
        return {"summary": "s", "why_good_lead": "w", "pitch": "p", "talking_points": ["a"], "draft_email": "e"}

    def _research(self, system_prompt: str, user_prompt: str) -> dict:
        """Record the prompts and return a fixed research answer."""
        self.system_prompts.append(system_prompt)
        self.prompts.append(user_prompt)
        return {"website": "https://example.com", "about": "a", "people": [], "sources": []}


def make_facts(**overrides) -> dict:
    """Made-up contractor facts as the database returns them; keyword arguments replace the defaults."""
    facts = {
        "name": "Example Roofing", "rating": 4.8, "review_count": 120, "certification": "Master Elite",
        "president_club_stars": 1, "commercial_certification": "GoldElite", "services": ["Metal", "Single-Ply"],
        "address": "1 Main St Newark, NJ 07101", "distance_miles": 9.5, "phone": "(555) 000-0000",
    }
    facts.update(overrides)
    return facts


def test_prompt_lists_the_facts_with_reviews_as_a_range():
    """The child receives every fact, and the review count only as a range."""
    provider = FakeProvider()
    provider.analyze(make_facts())
    prompt = provider.prompts[0]
    assert "- Rating: 4.8/5" in prompt
    assert "- Reviews: 100-499" in prompt
    assert "120" not in prompt
    assert "- President's Club: 1 star" in prompt
    assert "- Commercial certification: GoldElite" in prompt
    assert "- Product lines: Metal, Single-Ply" in prompt
    assert "- Address: 1 Main St Newark, NJ 07101" in prompt
    assert "- Distance: 9.5 miles" in prompt


def test_prompt_says_none_for_missing_data():
    """Missing facts are spelled out so the model does not guess."""
    provider = FakeProvider()
    provider.analyze(make_facts(
        rating=None, review_count=0, certification=None, president_club_stars=0, commercial_certification=None,
        services=[], address=None, distance_miles=None,
    ))
    prompt = provider.prompts[0]
    assert "- Rating: no reviews yet" in prompt
    assert "- Reviews: none" in prompt
    assert "- President's Club: none" in prompt
    assert "- Product lines: none" in prompt
    assert "- Certification: none" in prompt
    assert "- Address: unknown" in prompt
    assert "- Distance: unknown" in prompt


def test_prompt_adds_web_research_when_given():
    """Without research the prompt says so; with research it lists the website, notes and named people."""
    provider = FakeProvider()
    provider.analyze(make_facts())
    assert "- Website: not researched" in provider.prompts[0]
    research = {"website": "https://example.com", "about": "Roofing since 1998.", "people": ["Ann Lee (owner)"]}
    provider.analyze(make_facts(), research)
    assert "- Website: https://example.com" in provider.prompts[1]
    assert "- About (from their website): Roofing since 1998." in provider.prompts[1]
    assert "- People named on their website: Ann Lee (owner)" in provider.prompts[1]


def test_research_prompt_has_the_contact_details_and_todays_date():
    """The child gets the name, address and phone to identify the company, and the date for the search."""
    provider = FakeProvider()
    provider.research(make_facts())
    assert provider.prompts[0] == "Contractor: Example Roofing\nAddress: 1 Main St Newark, NJ 07101\nPhone: (555) 000-0000"
    assert provider.system_prompts[0].startswith("Today is 20")
    assert "{today}" not in provider.system_prompts[0]


def test_parent_class_cannot_be_used_directly():
    """AbstractAIProvider has no model, so analyze() and research() fail until a child writes them."""
    with pytest.raises(NotImplementedError):
        AbstractAIProvider().analyze(make_facts())
    with pytest.raises(NotImplementedError):
        AbstractAIProvider().research(make_facts())


def test_review_band_edges():
    """Each review count lands in the right band."""
    expected = {0: "none", 1: "1-9", 9: "1-9", 10: "10-49", 49: "10-49", 50: "50-99",
                99: "50-99", 100: "100-499", 499: "100-499", 500: "500+", 1330: "500+"}
    for count, band in expected.items():
        assert AbstractAIProvider().review_band(count) == band


def test_fingerprint_changes_only_for_facts_the_ai_uses():
    """Phone changes and a new review in the same band keep the fingerprint; a rating change does not."""
    provider = FakeProvider()
    base = provider.fingerprint(make_facts())
    assert provider.fingerprint(make_facts(phone="(555) 999-9999")) == base
    assert provider.fingerprint(make_facts(review_count=121)) == base
    assert provider.fingerprint(make_facts(review_count=500)) != base
    assert provider.fingerprint(make_facts(rating=4.9)) != base


def test_fingerprint_is_the_same_for_database_rows():
    """Decimal numbers and a different services order from PostgreSQL give the same fingerprint."""
    provider = FakeProvider()
    from_db = make_facts(rating=Decimal("4.8"), distance_miles=Decimal("9.50"), services=["Single-Ply", "Metal"])
    assert provider.fingerprint(from_db) == provider.fingerprint(make_facts())
