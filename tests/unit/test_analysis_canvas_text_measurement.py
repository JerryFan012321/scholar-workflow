"""Hand-counted v5 visible-text expectations, independent of tree layout.

At 280px, the existing 28px inset and 9px character estimate leave 28
Latin-width units. Fourteen CJK characters therefore occupy one 21px line;
24px padding and one extra click line give 66px. No paper or Vault is read.
Unsupported Markdown stays conservative rather than losing visible symbols.
"""

import pytest

from scholar_workflow.analysis.complete_reference import (
    _dimensions,
    _visible_lines,
    canvas_image_width,
    canvas_visible_height,
)
from scholar_workflow.analysis.reference_rendering import _visible_height as v4_height

CJK_LINE = "中" * 14


@pytest.mark.parametrize(
    "text",
    [
        CJK_LINE,
        f"**{CJK_LINE}**",
        f"[{CJK_LINE}](zotero://open-pdf/library/items/SYNTH001?page=1)",
        f"[[Synthetic Analysis#^synthetic|{CJK_LINE}]]",
        f"`{CJK_LINE}`",
    ],
)
def test_invisible_supported_syntax_does_not_add_a_wrapped_line(text):
    assert _visible_lines(text) == [CJK_LINE]
    assert canvas_visible_height(text, width=280) == 66
    assert _dimensions(text, "point") == (280, 66)


@pytest.mark.parametrize(
    ("text", "visible"),
    [
        ("**Task**", "Task"),
        ("**Synthetic title.** Full statement.", "Synthetic title. Full statement."),
        ("a_b*c#d", "a_b*c#d"),
        ("`a_b*c#d`", "a_b*c#d"),
        ("``a`b``", "a`b"),
        ("`[literal](not-a-source)`", "[literal](not-a-source)"),
        ("`[[literal|not-an-alias]]`", "[[literal|not-an-alias]]"),
        ("[literal](not a source)", "[literal](not a source)"),
        (r"\[literal](not-a-source)", "[literal](not-a-source)"),
        (r"\**literal**", "**literal**"),
        (r"\_literal\_", "_literal_"),
        ("**unclosed", "**unclosed"),
        ("`unclosed", "`unclosed"),
        ("** space **", "** space **"),
        ("***complex***", "***complex***"),
        ("# conservative heading", "# conservative heading"),
        ("A **complex inline** form", "A **complex inline** form"),
    ],
)
def test_literal_and_unsupported_syntax_cannot_be_silently_erased(text, visible):
    assert _visible_lines(text) == [visible]


@pytest.mark.parametrize("text", [r"\**" + CJK_LINE + "**", "`[" + "a" * 25 + "](x)`"])
def test_visible_literal_markers_still_wrap_at_the_boundary(text):
    # Respectively 32 and 30 visible units: both exceed 28 by hand count.
    assert canvas_visible_height(text, width=280) == 87


def test_blank_rows_and_click_line_remain_in_the_height():
    assert canvas_visible_height(f"**Task**\n\n{CJK_LINE}", width=280) == 108
    assert canvas_visible_height("", width=280) == 45
    assert canvas_visible_height("\n", width=280) == 66


@pytest.mark.parametrize("fence", ["```", "~~~~"])
@pytest.mark.parametrize("closed", [False, True])
def test_fenced_code_is_not_reinterpreted_as_links_or_bold(fence, closed):
    lines = [fence, "[literal](not-a-source)", "**literal**"]
    if closed:
        lines.append(fence)
    # Conservatively count the fence itself as well as every code character.
    assert _visible_lines("\n".join(lines)) == lines


def test_image_pixels_are_added_without_resizing_or_losing_caption_rows():
    text = "**Figure**\n![Synthetic|640x240](./attachments/synthetic.png)\n[Source](zotero://synthetic)"
    assert canvas_image_width(text) == 668
    assert canvas_visible_height(text, width=668) == 348
    assert _dimensions(text, "image") == (668, 348)


def test_v4_estimation_remains_unchanged():
    assert v4_height(f"**{CJK_LINE}**", minimum=0, width=280) == 87
