"""The priority score formula: four parts worth up to 25 points each. The orchestrator scores each scraped contractor; the API reads the stored parts."""

PRIOR_RATING = 4.0
PRIOR_REVIEWS = 100
CERTIFICATION_POINTS = {"Master Elite": 10, "Certified Plus": 5, "Certified": 0}
DISTANCE_HALF_POINTS_MILES = 25


def compute_scores(contractor: dict) -> dict[str, float]:
    """The four 25-point parts of the priority score and their total, each rounded to 2 decimals."""
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

    parts = {
        "review_count_adjusted_rating": review_points,
        "gaf_rank": gaf_rank_points,
        "specialty": specialty_points,
        "distance": distance_points,
    }
    # The total adds the unrounded parts, so it is as exact as possible.
    scores = {"priority_score": round(sum(parts.values()), 2)}
    for name in parts:
        scores[name] = round(parts[name], 2)
    return scores
