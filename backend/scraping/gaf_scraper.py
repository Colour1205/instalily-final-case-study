"""Fetches contractors from GAF's contractor finder (through its search service) and parses them.

Its only job is to scrape: it knows nothing about the database, the analysis queue, scores or rounding;
the orchestrator decides what happens to the results.
"""

import logging
import time

import httpx

from shared.settings import settings

log = logging.getLogger(__name__)

USER_AGENT = "LeadPlatformCaseStudy/0.1 (+https://github.com/Colour1205/instalily-final-case-study)"
MAX_RESULTS = 1000
MAX_ATTEMPTS = 4

COVEO_FIELDS = [
    "gaf_contractor_id", "gaf_navigation_title", "gaf_rating", "gaf_number_of_reviews",
    "gaf_address", "gaf_phone", "gaf_featured_image_src", "gaf_latitude", "gaf_longitude", "distanceinmiles",
    "gaf_residential_presidents_club_stars_count",
    "gaf_f_contractor_certifications_and_awards_residential",
    "gaf_f_contractor_certifications_and_awards_commercial",
    "gaf_f_contractor_designations_residential", "gaf_f_contractor_designations_commercial",
    "gaf_f_contractor_specialties_residential", "gaf_f_contractor_raq_specialties_residential",
    "gaf_contractor_attributes", "gaf_f_contractor_technologies_commercial",
]
RESIDENTIAL_CODE_FIELDS = [
    "gaf_f_contractor_designations_residential",
    "gaf_f_contractor_specialties_residential",
    "gaf_f_contractor_raq_specialties_residential",
    "gaf_contractor_attributes",
]

CERTIFICATION_TIERS = ("Master Elite", "Certified Plus", "Certified")
COMMERCIAL_CERTIFICATIONS = (
    ("PlatinumElite", "PLATINUMELITE"),
    ("GoldElite", "GOLDELITE"),
    ("Commercial Certified", "COMMERCIAL_CERTIFIED"),
    ("CoatingsPro Plus", "COATINGS_PRO_PLUS"),
    ("CoatingsPro", "COATINGS_PRO"),
)
RESIDENTIAL_LINES = {"FORTIFIED": "FORTIFIED", "METAL": "Metal", "SOLAR": "Solar"}
COMMERCIAL_LINES = {
    "Single-Ply Roofer": "Single-Ply",
    "Asphaltic Roofer": "Asphaltic",
    "Coatings & Liquid Applied": "Coatings",
}


class GAFScraper:
    """Gets every GAF contractor near one ZIP code and turns each search result into a contractor dictionary."""

    def __init__(self, zip_code: str) -> None:
        """Set up a scraper for one ZIP code from the configured list."""
        self.zip_code = zip_code
        self.latitude, self.longitude = settings.ZIP_COORDINATES[zip_code]

    def fetch(self) -> list[dict]:
        """Ask GAF's search service for every contractor in the radius and return them parsed."""
        data = self._helper_search()
        results = data.get("results", [])
        if data.get("totalCount", 0) > len(results):
            log.warning("GAF has %d contractors, only %d returned", data["totalCount"], len(results))

        contractors = []
        for result in results:
            try:
                contractor = self._parse_result(result)
            except (KeyError, TypeError, ValueError) as error:
                log.warning("Skipping bad result: %r", error)
                continue
            if not contractor["name"]:
                log.warning("Skipping contractor %s: no name", contractor["gaf_id"])
                continue
            contractors.append(contractor)
        return contractors

    def _parse_result(self, result: dict) -> dict:
        """Turn one search result into a contractor dictionary (column name to value), with GAF's numbers as given."""
        raw = result["raw"]
        reviews = int(raw.get("gaf_number_of_reviews") or 0)
        rating = None
        if reviews and raw.get("gaf_rating"):
            rating = float(raw["gaf_rating"])
        miles = raw.get("distanceinmiles")
        if miles is not None:
            miles = float(miles)
        # GAF points contractors without a photo at a placeholder image; treat that as no photo.
        logo_url = raw.get("gaf_featured_image_src")
        if logo_url and not logo_url.startswith("http"):
            logo_url = None

        return {
            "gaf_id": str(raw["gaf_contractor_id"]),
            "name": raw.get("gaf_navigation_title") or result.get("title"),
            "rating": rating,
            "review_count": reviews,
            "certification": self._helper_certification(raw),
            "president_club_stars": int(raw.get("gaf_residential_presidents_club_stars_count") or 0),
            "commercial_certification": self._helper_commercial_certification(raw),
            "services": self._helper_services(raw),
            "phone": raw.get("gaf_phone"),
            "address": raw.get("gaf_address"),
            "distance_miles": miles,
            "latitude": raw.get("gaf_latitude"),
            "longitude": raw.get("gaf_longitude"),
            "profile_url": result.get("uri"),
            "logo_url": logo_url,
        }

    def _helper_search(self) -> dict:
        """Send the search to GAF and return its JSON answer, retrying timeouts, 429 and 5xx with growing waits."""
        body = self._helper_search_body()
        headers = {"User-Agent": USER_AGENT, "Authorization": f"Bearer {settings.COVEO_API_KEY}"}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            problem = None
            try:
                response = httpx.post(
                    settings.COVEO_SEARCH_URL,
                    params={"organizationId": settings.COVEO_ORG_ID},
                    json=body,
                    headers=headers,
                    timeout=30,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    problem = f"HTTP {response.status_code}"
            except httpx.TransportError as error:
                problem = repr(error)
            if problem is None:
                break
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"GAF search failed: {problem}")
            log.warning("GAF search failed (%s), retrying in %d s", problem, 2 ** attempt)
            time.sleep(2 ** attempt)
        response.raise_for_status()
        return response.json()

    def _helper_search_body(self) -> dict:
        """The search request: every contractor within the radius of this ZIP code, nearest first."""
        return {
            "q": "",
            "aq": f"@distanceinmiles <= {settings.SEARCH_RADIUS_MILES} AND @gaf_f_country_code = USA",
            # dist() returns metres; the factor converts them to miles.
            "queryFunctions": [{
                "fieldName": "@distanceinmiles",
                "function": f"dist(@gaf_latitude, @gaf_longitude, {self.latitude}, {self.longitude})*0.000621371",
            }],
            "fieldsToInclude": COVEO_FIELDS,
            # GAF's own page sends the pipeline name as the search hub too.
            "pipeline": settings.COVEO_PIPELINE,
            "searchHub": settings.COVEO_PIPELINE,
            "sortCriteria": "@distanceinmiles ascending",
            "numberOfResults": MAX_RESULTS,
        }

    def _helper_certification(self, raw: dict) -> str | None:
        """The residential certification tier (Master Elite, Certified Plus or Certified), or None."""
        awards = " ".join(self._helper_as_list(raw.get("gaf_f_contractor_certifications_and_awards_residential")))
        for tier in CERTIFICATION_TIERS:
            if tier in awards:
                return tier
        return None

    def _helper_commercial_certification(self, raw: dict) -> str | None:
        """The highest commercial certification (for example GoldElite), or None."""
        commercial_codes = self._helper_codes(raw, ["gaf_f_contractor_designations_commercial"])
        commercial_awards = " ".join(self._helper_as_list(raw.get("gaf_f_contractor_certifications_and_awards_commercial")))
        for name, code in COMMERCIAL_CERTIFICATIONS:
            if code in commercial_codes or name in commercial_awards:
                return name
        return None

    def _helper_services(self, raw: dict) -> list[str]:
        """The product lines beyond shingles, such as Metal or Single-Ply, sorted by name."""
        residential_codes = self._helper_codes(raw, RESIDENTIAL_CODE_FIELDS)
        services = set()
        for code, name in RESIDENTIAL_LINES.items():
            if code in residential_codes:
                services.add(name)
        for roof_type in self._helper_as_list(raw.get("gaf_f_contractor_technologies_commercial")):
            if roof_type in COMMERCIAL_LINES:
                services.add(COMMERCIAL_LINES[roof_type])
        return sorted(services)

    def _helper_as_list(self, value) -> list:
        """Search fields hold one value or a list; always return a list."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _helper_codes(self, raw: dict, fields: list[str]) -> set[str]:
        """Collect designation codes such as 'METAL' from values like 'METAL^_^RESIDENTIAL^_^T'."""
        codes = set()
        for field in fields:
            for value in self._helper_as_list(raw.get(field)):
                codes.add(str(value).split("^_^")[0].upper())
        return codes
