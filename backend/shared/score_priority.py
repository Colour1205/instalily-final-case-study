"""The priority score formula: four parts worth up to 25 points each. Used by the scraper; the API reads the stored parts."""

PRIOR_RATING = 4.0
PRIOR_REVIEWS = 100
CERTIFICATION_POINTS = {"Master Elite": 10, "Certified Plus": 5, "Certified": 0}
DISTANCE_HALF_POINTS_MILES = 25


def score_parts(contractor: dict) -> dict[str, float]:
    """Work out the four 25-point parts of the priority score for one contractor."""
    reviews = contractor["review_count"]
    rating = contractor["rating"] or 0
    adjusted_rating = (rating * reviews + PRIOR_RATING * PRIOR_REVIEWS) / (reviews + PRIOR_REVIEWS)
    review_points = 25 * min(max(adjusted_rating - PRIOR_RATING, 0.0), 1.0)

    certification_points = CERTIFICATION_POINTS.get(contractor["certification"], 0)
    stars = contractor["president_club_stars"]
    club_points = 0
    if stars == 1:
        club_points = 10
    elif stars >= 2:
        club_points = 15
    gaf_rank_points = min(certification_points + club_points, 25)

    specialty_points = 25 * min(len(contractor["services"]), 3) / 3

    distance_points = 0.0
    if contractor["distance_miles"] is not None:
        distance_points = 25 / (1 + contractor["distance_miles"] / DISTANCE_HALF_POINTS_MILES)

    return {
        "review_count_adjust_rating": review_points,
        "gaf_rank": gaf_rank_points,
        "specialty": specialty_points,
        "distance": distance_points,
    }
