"""Unit tests for arXiv Atom parsing (pure, offline)."""
from __future__ import annotations
from scholar_workflow.adapters.arxiv import parse_arxiv_atom

_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <title>Attention Is All
    You Need</title>
    <published>2017-06-12T17:57:34Z</published>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <arxiv:doi>10.5555/3295222.3295349</arxiv:doi>
  </entry>
</feed>"""

_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>"""


def test_parse_full_entry():
    m = parse_arxiv_atom(_FEED)
    assert m["title"] == "Attention Is All You Need"  # whitespace collapsed
    assert m["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
    assert m["year"] == 2017
    assert m["doi"] == "10.5555/3295222.3295349"


def test_parse_no_entry_returns_empty():
    assert parse_arxiv_atom(_EMPTY) == {}


def test_parse_entry_without_doi():
    feed = _FEED.replace('<arxiv:doi>10.5555/3295222.3295349</arxiv:doi>', "")
    m = parse_arxiv_atom(feed)
    assert m["doi"] is None
    assert m["year"] == 2017
