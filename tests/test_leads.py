"""Tests for the leads API: the JSON shapes and the /v1 routes, using made-up data (no database)."""

from decimal import Decimal

import threading
import time

import redis
from fastapi.testclient import TestClient

from api import app
from leads import cache_leads, routes_leads
from leads.service_leads import LeadService

client = TestClient(app)
service = LeadService()


def make_row(**overrides) -> dict:
    """A made-up database row for one lead, as GET_LEAD returns it; keyword arguments replace the defaults."""
    row = {
        "gaf_id": "42", "name": "Example Roofing", "rating": Decimal("4.8"), "review_count": 120,
        "certification": "Master Elite", "president_club_stars": 1, "commercial_certification": None,
        "services": ["Metal", "Solar"], "distance_miles": Decimal("25.00"), "priority_score": Decimal("61.67"),
        "review_count_adjust_rating": Decimal("12.50"), "gaf_rank": Decimal("20.00"), "specialty": Decimal("16.67"),
        "distance": Decimal("12.50"),
        "logo_url": None, "phone": "(555) 000-0000", "address": "1 Main St Newark, NJ 07101",
        "profile_url": "https://example.com/42", "fingerprint": "abc",
        "summary": "s", "why_good_lead": "w", "pitch": "p", "talking_points": ["a", "b", "c"],
        "draft_email": "e", "analysis_fingerprint": "abc",
    }
    row.update(overrides)
    return row


def test_summary_has_plain_numbers_and_the_score_breakdown():
    """Decimals become floats, and the score has a total plus the four parts."""
    lead = service.lead_summary(make_row())
    assert lead["rating"] == 4.8
    assert lead["distance_miles"] == 25.0
    assert lead["score"]["total"] == 61.67
    assert lead["score"]["gaf_rank"] == 20
    assert lead["score"]["distance"] == 12.5
    assert lead["score"]["specialty"] == 16.67
    assert lead["summary"] == "s"
    assert set(lead["score"]) == {"total", "review_count_adjust_rating", "gaf_rank", "specialty", "distance"}


def test_detail_adds_contact_details_and_analysis():
    """The detail has a Maps link built from the address and says whether the analysis is current."""
    lead = service.lead_detail(make_row())
    assert lead["contact"]["maps_url"] == "https://www.google.com/maps/search/?api=1&query=1+Main+St+Newark%2C+NJ+07101"
    assert lead["analysis"]["is_current"] is True
    assert service.lead_detail(make_row(analysis_fingerprint="old"))["analysis"]["is_current"] is False


def test_detail_without_analysis_or_address():
    """A lead with no analysis yet still shows, with analysis set to null."""
    lead = service.lead_detail(make_row(summary=None, address=None))
    assert lead["analysis"] is None
    assert lead["contact"]["maps_url"] is None


def test_cache_keys_never_mix_up_different_filters():
    """One value containing a comma is not the same filter as two values; order and letter case do not matter."""
    base = {"q": None, "certifications": None, "services": None, "presidents_club": False,
            "min_rating": None, "max_distance": None}
    two = dict(base, certifications=["Certified", "Master Elite"])
    one = dict(base, certifications=["Certified,Master Elite"])
    swapped = dict(base, certifications=["Master Elite", "Certified"])
    assert service.filters_key(two) != service.filters_key(one)
    assert service.filters_key(two) == service.filters_key(swapped)
    assert service.filters_key(dict(base, q="Roof")) == service.filters_key(dict(base, q="roof"))


def test_sort_words_pick_which_score_parts_are_added_up():
    """No ranking words means all four parts (the priority score); otherwise only the chosen parts count."""
    assert service.sort_weights([]) == {"w_rating": 1, "w_rank": 1, "w_specialty": 1, "w_distance": 1}
    assert service.sort_weights(["rank", "specialty"]) == {"w_rating": 0, "w_rank": 1, "w_specialty": 1, "w_distance": 0}


def test_list_route_passes_the_ranking_and_rejects_unknown_words(monkeypatch):
    """Repeated sort values reach the service; a word that is not a score part is refused."""
    received = {}

    def fake_list_leads(page, limit, filters, sort):
        """Record the ranking and return an empty page."""
        received["sort"] = sort
        return {"page": page, "limit": limit, "total": 0, "leads": []}

    monkeypatch.setattr(routes_leads.lead_service, "list_leads", fake_list_leads)
    assert client.get("/v1/leads?sort=specialty&sort=rank").status_code == 200
    assert received["sort"] == ["specialty", "rank"]
    assert client.get("/v1/leads").status_code == 200
    assert received["sort"] == []
    assert client.get("/v1/leads?sort=price").status_code == 422


def test_list_route_passes_filters_and_returns_json(monkeypatch):
    """GET /v1/leads hands the page and every filter to the service and returns its JSON."""
    received = {}

    def fake_list_leads(page, limit, filters, sort):
        """Record the arguments and return a tiny page."""
        received["args"] = (page, limit, filters)
        return {"page": page, "limit": limit, "total": 0, "leads": []}

    monkeypatch.setattr(routes_leads.lead_service, "list_leads", fake_list_leads)
    query = "/v1/leads?page=2&limit=10&q=roof&certification=Master Elite&certification=Certified Plus"             "&service=Metal&service=&presidents_club=true&min_rating=4.5"
    response = client.get(query)
    assert response.status_code == 200
    assert response.json() == {"page": 2, "limit": 10, "total": 0, "leads": []}
    assert received["args"] == (2, 10, {
        "q": "roof", "certifications": ["Master Elite", "Certified Plus"], "services": ["Metal"],
        "presidents_club": True, "min_rating": 4.5, "max_distance": None,
    })


def test_map_route_returns_the_service_answer(monkeypatch):
    """GET /v1/map uses the same filters and returns the map JSON."""

    def fake_map_points(filters):
        """Return a tiny map answer."""
        return {"center": {"zip": "10013"}, "radius_miles": 25, "points": [], "max": filters["max_distance"]}

    monkeypatch.setattr(routes_leads.lead_service, "map_points", fake_map_points)
    assert client.get("/v1/map?max_distance=10").json()["max"] == 10


def test_only_the_github_pages_site_may_read_the_api_from_a_browser(monkeypatch):
    """The browser on GitHub Pages gets permission to read the API; any other website does not."""

    def fake_list_leads(page, limit, filters, sort):
        """Return an empty page."""
        return {"page": page, "limit": limit, "total": 0, "leads": []}

    monkeypatch.setattr(routes_leads.lead_service, "list_leads", fake_list_leads)
    allowed = client.get("/v1/leads", headers={"Origin": "https://colour1205.github.io"})
    assert allowed.headers.get("access-control-allow-origin") == "https://colour1205.github.io"
    other = client.get("/v1/leads", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in other.headers


def test_list_route_rejects_bad_values():
    """Out-of-range pages and limits, and an empty search, are refused before any database work."""
    assert client.get("/v1/leads", params={"limit": 500}).status_code == 422
    assert client.get("/v1/leads", params={"page": 0}).status_code == 422
    assert client.get("/v1/leads", params={"page": 10001}).status_code == 422
    assert client.get("/v1/leads", params={"q": ""}).status_code == 422


def test_unknown_lead_returns_404(monkeypatch):
    """GET /v1/leads/{gaf_id} returns 404 when the service finds nothing."""

    def fake_get_lead(gaf_id):
        """Pretend the id is unknown."""
        return None

    monkeypatch.setattr(routes_leads.lead_service, "get_lead", fake_get_lead)
    assert client.get("/v1/leads/does-not-exist").status_code == 404


class FakeRedis:
    """Stands in for Redis: a dictionary, with a lock so 'set if not exists' is safe across threads."""

    def __init__(self) -> None:
        """Start empty."""
        self.data = {}
        self.guard = threading.Lock()

    def get(self, key):
        """Return the stored value, or None."""
        return self.data.get(key)

    def set(self, key, value, nx=False, ex=None):
        """Store a value; with nx=True only if the key does not exist yet (returns None if it did)."""
        with self.guard:
            if nx and key in self.data:
                return None
            self.data[key] = value
            return True

    def exists(self, key):
        """1 if the key exists, else 0."""
        return int(key in self.data)

    def delete(self, key):
        """Remove the key if it exists."""
        self.data.pop(key, None)


class BrokenRedis:
    """Stands in for a Redis server that is down."""

    def get(self, key):
        """Fail like a lost connection."""
        raise redis.ConnectionError("down")

    def set(self, key, value, nx=False, ex=None):
        """Fail like a lost connection."""
        raise redis.ConnectionError("down")


class Counter:
    """Counts how often a fake database read runs."""

    def __init__(self) -> None:
        """Start at zero."""
        self.calls = 0

    def slow_read(self) -> dict:
        """Pretend to read the database (takes 0.2 s) and count the call."""
        self.calls += 1
        time.sleep(0.2)
        return {"total": 1, "leads": []}


def test_cached_answer_is_returned_without_building(monkeypatch):
    """Cache hit: the database read never runs."""
    fake_redis = FakeRedis()
    fake_redis.data["leads:v1:key"] = '{"total": 7}'
    monkeypatch.setattr(cache_leads, "redis_client", fake_redis)
    counter = Counter()
    assert cache_leads.LeadCache(60).get_or_build("leads:v1:key", counter.slow_read) == {"total": 7}
    assert counter.calls == 0


def test_only_one_of_many_requests_reads_the_database(monkeypatch):
    """Request coalescing: 10 requests miss at the same moment, only 1 reads the database, all get the answer."""
    fake_redis = FakeRedis()
    monkeypatch.setattr(cache_leads, "redis_client", fake_redis)
    cache = cache_leads.LeadCache(60)
    counter = Counter()
    answers = []

    def one_request():
        """Ask the cache for the page, like one API request."""
        answers.append(cache.get_or_build("leads:v1:key", counter.slow_read))

    threads = []
    for _ in range(10):
        thread = threading.Thread(target=one_request)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
    assert counter.calls == 1
    assert len(answers) == 10
    assert answers[0] == {"total": 1, "leads": []}
    assert answers[9] == {"total": 1, "leads": []}
    assert "lock:leads:v1:key" not in fake_redis.data


def test_waiters_build_themselves_when_the_builder_saves_nothing(monkeypatch):
    """If the lock disappears without an answer (unknown lead, or the builder failed), a waiter reads the database."""
    fake_redis = FakeRedis()
    fake_redis.data["lock:lead:v1:42"] = "1"
    monkeypatch.setattr(cache_leads, "redis_client", fake_redis)

    def unlock_soon():
        """Remove the lock after 0.1 s, as a builder that saved nothing would."""
        time.sleep(0.1)
        fake_redis.delete("lock:lead:v1:42")

    threading.Thread(target=unlock_soon).start()
    counter = Counter()
    assert cache_leads.LeadCache(60).get_or_build("lead:v1:42", counter.slow_read) == {"total": 1, "leads": []}
    assert counter.calls == 1


def test_redis_down_means_reading_the_database(monkeypatch):
    """A Redis failure means 'not cached', never an error for the rep."""
    monkeypatch.setattr(cache_leads, "redis_client", BrokenRedis())
    counter = Counter()
    assert cache_leads.LeadCache(60).get_or_build("lead:v1:42", counter.slow_read) == {"total": 1, "leads": []}
    assert counter.calls == 1
