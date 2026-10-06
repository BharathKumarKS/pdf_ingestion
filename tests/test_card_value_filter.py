"""Cards must stand alone — the value filter, and the prompt bug it compensates for.

The generator prompt required *answers* to be interpretable out of context but said
nothing about *questions*, so the model anchored questions to the source. On the
Feynman corpus that produced 8,503 cards (8.9%), 7,551 of them question cards, that a
student cannot use. These tests pin the filter that drops them at generation time.
"""
import json
import uuid

import pytest


def _chunk():
    from src.pdf_ingestion.chunker import TextChunk
    return TextChunk(
        chunk_id=str(uuid.uuid4()),
        document_id="doc-1",
        tenant_id="global",
        chunk_index=0,
        text="Newton's second law: force equals mass times acceleration.",
        char_start=0,
        char_end=60,
        token_count=10,
        page_number=1,
    )


class TestIsValuable:
    def test_rejects_source_reference(self):
        from src.pdf_ingestion.card_generator import ResponseParser
        assert not ResponseParser.is_valuable(
            "According to the passage, what shines through all of Feynman's work?", ""
        )

    @pytest.mark.parametrize("question", [
        "What does the text state about energy?",
        "How is the effect described in this excerpt?",
        "What does the author mention about momentum?",
        "This passage describes which phenomenon?",
        "What is explained in the text?",
    ])
    def test_rejects_each_banned_phrasing(self, question):
        from src.pdf_ingestion.card_generator import ResponseParser
        assert not ResponseParser.is_valuable(question, "a reasonable answer here")

    def test_keeps_the_passage_of_time_idiom(self):
        """A naive `the passage` regex would delete legitimate physics cards."""
        from src.pdf_ingestion.card_generator import ResponseParser
        assert ResponseParser.is_valuable(
            "How might the passage of time have affected memories of Feynman's lectures?",
            "Memories of the lectures may have faded with the passage of time.",
        )

    def test_rejects_too_short(self):
        from src.pdf_ingestion.card_generator import ResponseParser
        assert not ResponseParser.is_valuable("Short.", "tiny")

    def test_accepts_a_good_card(self):
        from src.pdf_ingestion.card_generator import ResponseParser
        assert ResponseParser.is_valuable(
            "How does a 2 % reflection coefficient affect a light beam's intensity?",
            "It reduces the transmitted intensity by about 2 %.",
        )


class TestParsersDropJunk:
    def test_qa_pairs_drop_source_references(self):
        from src.pdf_ingestion.card_generator import ResponseParser
        raw = json.dumps([
            {"question": "According to the passage, what is inertia?",
             "answer": "Inertia is the resistance to a change in motion."},
            {"question": "What is inertia?",
             "answer": "Inertia is an object's resistance to a change in its motion."},
        ])
        cards = ResponseParser.parse_qa_pairs(raw, _chunk())
        assert len(cards) == 1
        assert cards[0].content == "What is inertia?"

    def test_factoids_drop_short_text(self):
        from src.pdf_ingestion.card_generator import ResponseParser
        raw = json.dumps(["ok", "Newton's second law relates force, mass and acceleration."])
        cards = ResponseParser.parse_factoids(raw, _chunk())
        assert len(cards) == 1

    def test_formula_exempt_from_length_floor(self):
        """'E = mc²' is a valid card even though it is short."""
        from src.pdf_ingestion.card_generator import ResponseParser, CardType
        raw = json.dumps({"title": "Mass-energy", "content": "E = mc²"})
        cards = ResponseParser.parse_single_object(raw, _chunk(), CardType.FORMULA)
        assert len(cards) == 1

    def test_non_formula_still_length_filtered(self):
        from src.pdf_ingestion.card_generator import ResponseParser, CardType
        raw = json.dumps({"title": "Tiny", "content": "E = mc²"})
        cards = ResponseParser.parse_single_object(raw, _chunk(), CardType.DEFINITION)
        assert cards == []
