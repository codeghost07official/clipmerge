import unittest

from keyword_engine import build_search_queries
from media_pipeline import PexelsClient, score_candidate_relevance


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

    def test_candidate_from_video_prefers_lower_resolution_when_available(self):
        client = PexelsClient("test-key")
        video = {
            "id": 999,
            "duration": 8,
            "url": "https://example.com/video",
            "user": {"name": "Test Creator"},
            "video_files": [
                {"file_type": "video/mp4", "link": "https://example.com/hd.mp4", "width": 1080, "height": 1920},
                {"file_type": "video/mp4", "link": "https://example.com/low.mp4", "width": 720, "height": 1280},
            ],
        }

        candidate = client._candidate_from_video(video, "test", "portrait", set())

        self.assertEqual(candidate.width, 720)
        self.assertEqual(candidate.height, 1280)


if __name__ == "__main__":
    unittest.main()
