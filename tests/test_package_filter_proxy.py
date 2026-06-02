"""Regression tests for _PackageFilterProxy filter state.

Tests that category and tag filters are mutually exclusive (selecting one
always clears the other) and that "All" correctly resets both.
"""
from __future__ import annotations

import pytest

# _PackageFilterProxy is an internal class — import directly for unit testing
from views.packages_view import _PackageFilterProxy

_ALL = ""


# ── Filter state: category ────────────────────────────────────────────────────

def test_set_category_clears_tag():
    proxy = _PackageFilterProxy()
    proxy.set_filter(category="Games", tag_name="")
    proxy.set_filter(category="", tag_name="Work")
    # Now set category — tag must be cleared
    proxy.set_filter(category="Games", tag_name=_ALL)
    assert proxy.current_tag() == _ALL
    assert proxy.current_category() == "Games"


def test_set_tag_clears_category():
    proxy = _PackageFilterProxy()
    proxy.set_filter(category="Games", tag_name=_ALL)
    # Now set tag — category must be cleared
    proxy.set_filter(category=_ALL, tag_name="Work")
    assert proxy.current_category() == _ALL
    assert proxy.current_tag() == "Work"


def test_all_categories_resets_category_filter():
    proxy = _PackageFilterProxy()
    proxy.set_filter(category="Games", tag_name=_ALL)
    proxy.set_filter(category=_ALL, tag_name=_ALL)
    assert proxy.current_category() == _ALL


def test_all_tags_resets_tag_filter():
    proxy = _PackageFilterProxy()
    proxy.set_filter(category=_ALL, tag_name="Work")
    proxy.set_filter(category=_ALL, tag_name=_ALL)
    assert proxy.current_tag() == _ALL


# ── Default state ─────────────────────────────────────────────────────────────

def test_initial_state_is_all():
    proxy = _PackageFilterProxy()
    assert proxy.current_category() == _ALL
    assert proxy.current_tag() == _ALL
