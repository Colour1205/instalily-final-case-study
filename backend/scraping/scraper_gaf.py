"""Fetches contractors from GAF's contractor finder (through its search service) and scores them.

Knows nothing about the database or the AI queue; the orchestrator decides what happens to the results.
"""

import logging
import time

import httpx

from shared.config import settings
from shared.score_priority import priority_score

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
    """Gets every GAF contractor near one ZIP code and turns each into a scored contractor row."""

    def __init__(self, zip_code: str) -> None:
        """Set up a scraper for one ZIP code from the configured list."""
        self.zip_code = zip_code
        self.latitude, self.longitude = settings.zip_coordinates[zip_code]

    def fetch(self) -> list[dict]:
        """Ask GAF's search service for every contractor in the radius; return them parsed and scored."""
        body = {
            "q": "",
            "aq": f"@distanceinmiles <= {settings.search_radius_miles} AND @gaf_f_country_code = USA",
            # dist() returns metres; the factor converts them to miles.
            "queryFunctions": [{
                "fieldName": "@distanceinmiles",
                "function": f"dist(@gaf_latitude, @gaf_longitude, {self.latitude}, {self.longitude})*0.000621371",
            }],
            "fieldsToInclude": COVEO_FIELDS,
            # GAF's own page sends the pipeline name as the search hub too.
            "pipeline": settings.coveo_pipeline,
            "searchHub": settings.coveo_pipeline,
            "sortCriteria": "@distanceinmiles ascending",
            "numberOfResults": MAX_RESULTS,
        }
        headers = {"User-Agent": USER_AGENT, "Authorization": f"Bearer {settings.coveo_api_key}"}

        # Retry timeouts, "too many requests" (429) and server errors (5xx), waiting longer each time.
        for attempt in range(1, MAX_ATTEMPTS + 1):
            problem = None
            try:
                response = httpx.post(
                    settings.coveo_search_url,
                    params={"organizationId": settings.coveo_org_id},
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
        data = response.json()

        results = data.get("results", [])
        if data.get("totalCount", 0) > len(results):
            log.warning("GAF has %d contractors, only %d returned", data["totalCount"], len(results))

        contractors = []
        for result in results:
            try:
                contractor = self.parse_result(result)
            except (KeyError, TypeError, ValueError) as error:
                log.warning("Skipping bad result: %r", error)
                continue
            if not contractor["name"]:
                log.warning("Skipping contractor %s: no name", contractor["gaf_id"])
                continue
            contractor["priority_score"] = priority_score(contractor)
            contractors.append(contractor)
        return contractors

    def parse_result(self, result: dict) -> dict:
        """Turn one search result into a contractor row (column name to value)."""
        raw = result["raw"]
        reviews = int(raw.get("gaf_number_of_reviews") or 0)
        rating = None
        if reviews and raw.get("gaf_rating"):
            rating = round(float(raw["gaf_rating"]), 1)
        miles = raw.get("distanceinmiles")
        if miles is not None:
            miles = round(float(miles), 2)
        # GAF points contractors without a photo at a placeholder image; treat that as no photo.
        logo_url = raw.get("gaf_featured_image_src")
        if logo_url and not logo_url.startswith("http"):
            logo_url = None

        awards = " ".join(self.as_list(raw.get("gaf_f_contractor_certifications_and_awards_residential")))
        certification = None
        for tier in CERTIFICATION_TIERS:
            if tier in awards:
                certification = tier
                break

        commercial_codes = self.codes(raw, ["gaf_f_contractor_designations_commercial"])
        commercial_awards = " ".join(self.as_list(raw.get("gaf_f_contractor_certifications_and_awards_commercial")))
        commercial_certification = None
        for name, code in COMMERCIAL_CERTIFICATIONS:
            if code in commercial_codes or name in commercial_awards:
                commercial_certification = name
                break

        residential_codes = self.codes(raw, RESIDENTIAL_CODE_FIELDS)
        services = set()
        for code, name in RESIDENTIAL_LINES.items():
            if code in residential_codes:
                services.add(name)
        for roof_type in self.as_list(raw.get("gaf_f_contractor_technologies_commercial")):
            if roof_type in COMMERCIAL_LINES:
                services.add(COMMERCIAL_LINES[roof_type])

        return {
            "gaf_id": str(raw["gaf_contractor_id"]),
            "name": raw.get("gaf_navigation_title") or result.get("title"),
            "rating": rating,
            "review_count": reviews,
            "certification": certification,
            "president_club_stars": int(raw.get("gaf_residential_presidents_club_stars_count") or 0),
            "commercial_certification": commercial_certification,
            "services": sorted(services),
            "phone": raw.get("gaf_phone"),
            "address": raw.get("gaf_address"),
            "distance_miles": miles,
            "latitude": raw.get("gaf_latitude"),
            "longitude": raw.get("gaf_longitude"),
            "profile_url": result.get("uri"),
            "logo_url": logo_url,
        }

    def as_list(self, value) -> list:
        """Search fields hold one value or a list; always return a list."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def codes(self, raw: dict, fields: list[str]) -> set[str]:
        """Collect designation codes such as 'METAL' from values like 'METAL^_^RESIDENTIAL^_^T'."""
        codes = set()
        for field in fields:
            for value in self.as_list(raw.get(field)):
                codes.add(str(value).split("^_^")[0].upper())
        return codes
