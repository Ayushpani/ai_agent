"""The narrator's prose is shown to the employee verbatim, so a model
writing its plan for the answer into the answer is a user-visible defect.
Observed in practice with a free-tier narrator.
"""
from app.graph.llm_output import strip_scaffolding


def test_strips_the_exact_leak_seen_in_the_ui():
    raw = (
        "Let's craft:\n\n"
        "Direct answer: Principal outstanding is almost evenly spread across the four regions.\n\n"
        "Findings in order of importance:\n\n"
        "The concentration index is 0.2501, close to the theoretical minimum."
    )
    cleaned = strip_scaffolding(raw)

    assert "Let's craft" not in cleaned
    assert "Direct answer:" not in cleaned
    assert "Findings in order of importance" not in cleaned
    assert cleaned.startswith("Principal outstanding is almost evenly spread")
    assert "concentration index is 0.2501" in cleaned


def test_keeps_content_on_a_labelled_line():
    """The label goes; the sentence after it must not."""
    assert strip_scaffolding("Answer: POS rose 8%.") == "POS rose 8%."


def test_clean_prose_is_untouched():
    prose = (
        "Finance-level 90+ AUM rose 8.4% over the window.\n\n"
        "The branch breakdown shows the movement is concentrated."
    )
    assert strip_scaffolding(prose) == prose


def test_does_not_eat_a_sentence_that_merely_starts_similarly():
    """Only a line that is ENTIRELY scaffolding is dropped — a real
    sentence beginning with a similar word must survive."""
    prose = "Draft loan agreements accounted for 4% of the book."
    assert strip_scaffolding(prose) == prose


def test_collapses_blank_runs_left_behind():
    raw = "Let's craft:\n\n\n\nPOS was flat."
    assert strip_scaffolding(raw) == "POS was flat."


def test_empty_input_is_safe():
    assert strip_scaffolding("") == ""
    assert strip_scaffolding("   \n  ") == ""
