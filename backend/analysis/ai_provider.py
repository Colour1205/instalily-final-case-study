"""Parent class for AI providers (strategy pattern). Child classes only send the prompt to one model.

Knows nothing about the database or the job queue.
"""

import hashlib
import json

# Bump this when the prompt changes, so every contractor gets a fresh analysis.
PROMPT_VERSION = 3

# Facts sent to the AI. An analysis is reused until one of these changes.
AI_FACT_FIELDS = (
    "name", "rating", "review_count", "certification", "president_club_stars",
    "commercial_certification", "services", "address", "distance_miles",
)
REVIEW_BAND_EDGES = (1, 10, 50, 100, 500)

SYSTEM_PROMPT = """You write short account-planning notes for sales reps at a roofing materials distributor in the New York City area. It sells shingle roof systems, GAF warranty-eligible systems and commercial roofing products (single-ply, asphaltic, coatings, insulation) to roofing contractors.

You get facts about one contractor from GAF's directory. Help a rep decide whether to call and what to say.

Rules:
- Use only the given facts. Never invent names, job titles, revenue, staff numbers, years in business, past projects or current suppliers.
- Name a person only if "People named on their website" lists them. The first talking point must say who to ask for: that person and their role, or otherwise the role to ask for (for example the owner, the estimator or the purchasing manager) and why, based on how big the contractor looks.
- Mention only certifications and awards the contractor holds. Skip any listed as "none".
- Reviews are given as a range. Use the range, never an exact number.
- Distance is from the centre of the sales area, not from a warehouse. Never say where the distributor is, and never promise delivery times, prices or terms.
- Certification, President's Club and reviews are rough signs of size. Say "suggests", not "proves".
- Plain text, no markdown.

Background:
- Certified contractors offer the System Plus warranty, Certified Plus also offer Silver Pledge, and Master Elite also offer Golden Pledge. These warranties need a minimum amount of GAF products.
- President's Club is GAF's award for top Master Elite contractors.
- FORTIFIED means storm-resistant roofs. Metal, Solar, Single-Ply, Asphaltic and Coatings are product lines.

Fields:
- summary: 1-2 sentences about the business itself: what work it does, where, and how big and well regarded it looks. Use "About (from their website)" when given. Do not start with the company name, and do not name its GAF certification, awards or product lines: the rep already sees those as badges.
- why_good_lead: 2-3 sentences on why they are worth a call.
- pitch: 2-3 sentences on which product lines to lead with.
- talking_points: 3-5 one-sentence points for a first call.
- draft_email: under 150 words. First line "Subject: ...". Start with "Hello <first name>," if a person is named, otherwise "Hello <company name> team,". Sign "[Your name]".

Example
Facts:
- Name: Harborview Roofing LLC
- Address: 12 River St Hoboken, NJ 07030
- Distance: 3.1 miles
- Certification: Master Elite
- President's Club: 1 star
- Commercial certification: GoldElite
- Rating: 4.8/5
- Reviews: 100-499
- Product lines: Asphaltic, Single-Ply
- Website: https://harborviewroofing.example
- About (from their website): Family-owned roofing and siding company serving Hudson County since 1998.
- People named on their website: Maria Lopez (owner)
Answer:
{"summary": "A family-owned Hoboken roofing and siding company serving Hudson County since 1998, with a large, well-rated homeowner following and a side line in flat commercial roofs.", "why_good_lead": "Master Elite and President's Club put them among GAF's top contractors, and GoldElite certification suggests steady commercial work. A 4.8 rating points to strong demand.", "pitch": "Lead with Golden Pledge-eligible shingle systems for their homes, then single-ply and asphaltic systems for their commercial jobs.", "talking_points": ["Ask for Maria Lopez, the owner named on their website: at a family-owned company she likely chooses suppliers.", "Congratulate them on their President's Club award.", "Ask how they source materials for Golden Pledge jobs.", "Offer single-ply and asphaltic products for their commercial work.", "Ask how they get materials to job sites around Hoboken."], "draft_email": "Subject: Supplying your Golden Pledge and commercial jobs\\n\\nHello Maria,\\n\\nCongratulations on your President's Club award. As a Master Elite and GoldElite contractor, you need reliable supply for both homes and commercial roofs. We stock complete GAF warranty-eligible shingle systems, plus single-ply and asphaltic systems.\\n\\nCould we set up a 15-minute call about your upcoming jobs?\\n\\nBest regards,\\n[Your name]"}

Example
Facts:
- Name: Northline Exteriors
- Address: 45 Main St Yonkers, NY 10701
- Distance: 14.2 miles
- Certification: Certified
- President's Club: none
- Commercial certification: none
- Rating: no reviews yet
- Reviews: none
- Product lines: none
- Website: not researched
Answer:
{"summary": "A small or newer Yonkers exteriors company with no homeowner reviews yet. The name suggests work beyond roofing, such as siding or windows.", "why_good_lead": "As a GAF Certified contractor they need GAF products to offer the System Plus warranty. A smaller contractor may not have a fixed supplier yet.", "pitch": "Lead with complete System Plus-eligible shingle systems that can be ordered in one place.", "talking_points": ["Ask for the owner: at a smaller contractor the owner usually chooses suppliers.", "Ask what kinds of residential jobs they focus on.", "Explain how a full System Plus system can be ordered at once.", "Ask how they get materials to job sites today."], "draft_email": "Subject: Making System Plus jobs easier to supply\\n\\nHello Northline Exteriors team,\\n\\nAs a GAF Certified contractor, you can offer the System Plus warranty, and we can supply every part of those roof systems in one order.\\n\\nWould you be open to a quick call about your upcoming jobs?\\n\\nBest regards,\\n[Your name]"}"""


# The JSON shape every AI provider must return (a JSON Schema, which Claude's structured output follows).
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "why_good_lead": {"type": "string"},
        "pitch": {"type": "string"},
        "talking_points": {"type": "array", "items": {"type": "string"}},
        "draft_email": {"type": "string"},
    },
    "required": ["summary", "why_good_lead", "pitch", "talking_points", "draft_email"],
    "additionalProperties": False,
}


class AbstractAIProvider:
    """Turns one contractor's facts into a sales analysis. Not used directly: each child writes _generate."""

    # Each child sets the name of the model it asks; it is part of the fingerprint.
    model = ""

    def analyze(self, facts: dict) -> dict:
        """Build the prompt from one contractor's facts and return the model's analysis as a dictionary."""
        stars = int(facts["president_club_stars"])
        presidents_club = "none"
        if stars == 1:
            presidents_club = "1 star"
        elif stars > 1:
            presidents_club = f"{stars} stars"
        rating = "no reviews yet"
        if facts["rating"] is not None:
            rating = f"{round(float(facts['rating']), 1)}/5"
        distance = "unknown"
        if facts["distance_miles"] is not None:
            distance = f"{round(float(facts['distance_miles']), 1)} miles"

        lines = [
            f"Name: {facts['name']}",
            f"Address: {facts['address'] or 'unknown'}",
            f"Distance: {distance}",
            f"Certification: {facts['certification'] or 'none'}",
            f"President's Club: {presidents_club}",
            f"Commercial certification: {facts['commercial_certification'] or 'none'}",
            f"Rating: {rating}",
            f"Reviews: {self.review_band(facts['review_count'])}",
            f"Product lines: {', '.join(facts['services']) or 'none'}",
            # Always this line: the fine-tuned local model (lili-analyst) was trained with prompt v3, which has it.
            "Website: not researched",
        ]
        prompt = "Facts:\n"
        for line in lines:
            prompt += "- " + line + "\n"
        return self._generate(SYSTEM_PROMPT, prompt)

    def _generate(self, system_prompt: str, user_prompt: str) -> dict:
        """Send the prompts to the model and return its JSON answer. Every child class must write its own version."""
        raise NotImplementedError("Each AI provider must write _generate")

    def review_band(self, review_count: int) -> str:
        """Group a review count into none, 1-9, 10-49, 50-99, 100-499 or 500+."""
        review_count = int(review_count)
        if review_count == 0:
            return "none"
        for i in range(len(REVIEW_BAND_EDGES) - 1):
            low = REVIEW_BAND_EDGES[i]
            high = REVIEW_BAND_EDGES[i + 1]
            if review_count < high:
                return f"{low}-{high - 1}"
        return f"{REVIEW_BAND_EDGES[-1]}+"

    def fingerprint(self, contractor: dict) -> str:
        """Fingerprint of exactly what the AI is told and which model answers, so unchanged facts need no new analysis."""
        facts = {}
        for field in AI_FACT_FIELDS:
            facts[field] = contractor[field]
        # Same types and rounding as the prompt, whether the facts came from GAF or from PostgreSQL.
        if facts["rating"] is not None:
            facts["rating"] = float(facts["rating"])
        if facts["distance_miles"] is not None:
            facts["distance_miles"] = round(float(facts["distance_miles"]), 1)
        facts["review_count"] = self.review_band(facts["review_count"])
        facts["president_club_stars"] = int(facts["president_club_stars"])
        facts["services"] = sorted(facts["services"])
        facts["prompt_version"] = PROMPT_VERSION
        facts["model"] = self.model
        return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()
