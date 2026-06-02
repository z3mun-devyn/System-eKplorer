"""Unit tests for package_query.parse()."""

import pytest
from package_query import PackageQuery, parse, EMPTY


# ── Empty / whitespace ────────────────────────────────────────────────────────

def test_empty_string_returns_empty():
    assert parse("") == EMPTY


def test_whitespace_only_returns_empty():
    assert parse("   ") == EMPTY


# ── Free-text name ────────────────────────────────────────────────────────────

def test_single_word_goes_to_name():
    q = parse("firefox")
    assert q.name == "firefox"
    assert q.tag == q.category == q.source == q.version == q.size == ""


def test_multi_word_free_text_joined_by_space():
    q = parse("my special pkg")
    assert q.name == "my special pkg"


def test_name_is_lowercased():
    q = parse("Firefox")
    assert q.name == "firefox"


# ── Individual modifiers ──────────────────────────────────────────────────────

def test_tagged_modifier():
    q = parse("tagged:essential")
    assert q.tag == "essential"
    assert q.name == ""


def test_category_modifier():
    q = parse("category:games")
    assert q.category == "games"


def test_source_modifier():
    q = parse("source:flatpak")
    assert q.source == "flatpak"


def test_version_modifier():
    q = parse("version:1.2.3")
    assert q.version == "1.2.3"


def test_size_modifier():
    q = parse("size:10mb")
    assert q.size == "10mb"


# ── Case insensitivity of modifier names ──────────────────────────────────────

def test_uppercase_modifier_name():
    q = parse("TAGGED:essential")
    assert q.tag == "essential"


def test_mixed_case_modifier_name():
    q = parse("Category:games")
    assert q.category == "games"


# ── Lenient space after colon ("tagged: essential") ──────────────────────────

def test_tagged_with_space_after_colon():
    q = parse("tagged: essential")
    assert q.tag == "essential"
    assert q.name == ""


def test_source_with_space_after_colon():
    q = parse("source: flatpak")
    assert q.source == "flatpak"


# ── Combined modifiers ────────────────────────────────────────────────────────

def test_two_modifiers_no_name():
    q = parse("source:flatpak category:games")
    assert q.source == "flatpak"
    assert q.category == "games"
    assert q.name == ""


def test_modifier_and_free_text():
    q = parse("tagged:essential firefox")
    assert q.tag == "essential"
    assert q.name == "firefox"


def test_free_text_before_modifier():
    q = parse("firefox tagged:essential")
    assert q.name == "firefox"
    assert q.tag == "essential"


def test_all_five_modifiers():
    q = parse("tagged:t category:c source:s version:v size:z")
    assert q.tag == "t"
    assert q.category == "c"
    assert q.source == "s"
    assert q.version == "v"
    assert q.size == "z"


# ── Unknown modifier falls through as free text ───────────────────────────────

def test_unknown_modifier_becomes_name():
    q = parse("colour:red firefox")
    assert "colour:red" in q.name
    assert "firefox" in q.name


def test_unknown_modifier_only():
    q = parse("colour:red")
    assert q.name == "colour:red"
    assert q.tag == q.category == q.source == ""


# ── Trailing modifier with no value ──────────────────────────────────────────

def test_trailing_tagged_colon_no_crash():
    q = parse("tagged:")
    assert q.tag == ""  # empty, not an error


def test_trailing_category_colon_no_crash():
    q = parse("category:")
    assert q.category == ""


def test_modifier_colon_then_another_modifier():
    # "tagged: source:flatpak" — "source:flatpak" is consumed as the tag value
    q = parse("tagged: source:flatpak")
    assert q.tag == "source:flatpak"
    assert q.source == ""  # never reached as its own modifier


def test_modifier_value_is_lowercased():
    q = parse("tagged:Essential")
    assert q.tag == "essential"
