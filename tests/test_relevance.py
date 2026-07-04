import unittest

from keyword_engine import build_search_queries
from media_pipeline import score_candidate_relevance


class RelevancePipelineTests(unittest.TestCase):
    def test_build_search_queries_preserves_prompt_concepts(self):
        prompt = "Astronauts exploring the Moon while Earth rises on the horizon with cinematic space shots."
        queries = build_search_queries(prompt, max_keywords=12)
        joined = " ".join(queries)

        self.assertGreaterEqual(len(queries), 6)
        self.assertIn("astronaut", joined)
        self.assertIn("moon", joined)
        self.assertIn("earth", joined)
        self.assertIn("space", joined)

    def test_score_candidate_relevance_prefers_prompt_matches(self):
        prompt_terms = {"astronaut", "moon", "space", "earth"}
        score = score_candidate_relevance(["astronaut", "moon", "space"], "astronaut moon", prompt_terms)
        self.assertGreater(score, 0)


if __name__ == "__main__":
    unittest.main()
