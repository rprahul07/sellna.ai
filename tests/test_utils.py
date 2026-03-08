"""Tests for text cleaning utilities."""

from app.utils.text_cleaning import (
    clean_text,
    deduplicate_list,
    extract_sentences,
    normalize_whitespace,
    truncate,
)


def test_clean_text_removes_html_entities():
    assert clean_text("Hello &amp; World") == "Hello & World"
    assert clean_text("&lt;p&gt;Test&lt;/p&gt;") == "<p>Test</p>"
    assert clean_text("Don&apos;t stop") == "Don&apos;t stop"  # &apos; not in list


def test_clean_text_strips_whitespace():
    assert clean_text("  hello  ") == "hello"
    assert clean_text("\u00a0text\u00a0") == "text"


def test_normalize_whitespace():
    assert normalize_whitespace("hello   world") == "hello world"
    assert normalize_whitespace("line\n\n\n\nbreak") == "line\n\nbreak"


def test_deduplicate_list_preserves_order():
    result = deduplicate_list(["a", "b", "a", "c", "B"])
    assert result == ["a", "b", "c", "B"]


def test_deduplicate_list_case_sensitive():
    result = deduplicate_list(["A", "a"], case_sensitive=True)
    assert result == ["A", "a"]


def test_truncate():
    text = "word " * 100
    result = truncate(text, max_chars=50)
    assert len(result) <= 51  # may be slightly over due to ellipsis
    assert result.endswith("…")


def test_truncate_short_text():
    short = "Hello"
    assert truncate(short, max_chars=100) == "Hello"


def test_extract_sentences():
    text = "First sentence. Second sentence! Third sentence? Fourth."
    result = extract_sentences(text, max_sentences=2)
    assert len(result) <= 2
    assert "First sentence" in result[0]
