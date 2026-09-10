from app.graph.llm_output import extract_json_object


def test_clean_json_extracted_as_is():
    raw = '{"intent": "trend", "requires_chart": true}'
    assert extract_json_object(raw) == {"intent": "trend", "requires_chart": True}


def test_json_in_fenced_block_extracted():
    raw = 'Here you go:\n```json\n{"intent": "lookup"}\n```\nHope that helps.'
    assert extract_json_object(raw) == {"intent": "lookup"}


def test_reasoning_preamble_before_json_is_skipped():
    raw = (
        "Let me think about this question step by step. It mentions AUM "
        "without a level, so I should flag ambiguity.\n\n"
        '{"intent": "aggregation", "ambiguous_aggregation_level": true}'
    )
    assert extract_json_object(raw) == {
        "intent": "aggregation", "ambiguous_aggregation_level": True
    }


def test_nested_braces_handled_correctly():
    raw = '{"error": "insufficient_schema", "missing": "a column with a {weird} name"}'
    assert extract_json_object(raw) == {
        "error": "insufficient_schema", "missing": "a column with a {weird} name"
    }


def test_no_json_present_returns_none():
    raw = "I cannot answer this question, sorry."
    assert extract_json_object(raw) is None


def test_malformed_json_skipped_in_favor_of_next_candidate():
    raw = '{not valid json} then later {"intent": "lookup"}'
    assert extract_json_object(raw) == {"intent": "lookup"}
