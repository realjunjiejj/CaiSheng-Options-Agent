"""Unit tests verifying academic research bibliography and paper grounding."""

import pytest
from volagent.research.bibliography import (
    RESEARCH_BIBLIOGRAPHY,
    get_paper_by_id,
    get_papers_by_category,
)


def test_research_bibliography_contains_all_core_papers():
    """Verify that all core quantitative finance and AI debate papers are registered."""
    assert len(RESEARCH_BIBLIOGRAPHY) >= 8
    
    paper_ids = {p.paper_id for p in RESEARCH_BIBLIOGRAPHY}
    assert "CARR-WU-2009" in paper_ids
    assert "BRENNER-SUBRAHMANYAM-1988" in paper_ids
    assert "JAMES-STEIN-1961" in paper_ids
    assert "ROCKAFELLAR-URYASEV-2000" in paper_ids
    assert "ARTZNER-1999" in paper_ids
    assert "DU-2023" in paper_ids
    assert "GAO-2023" in paper_ids
    assert "NATENBERG-1994" in paper_ids


def test_get_paper_by_id_and_category():
    """Verify lookup helpers in academic bibliography."""
    paper = get_paper_by_id("CARR-WU-2009")
    assert paper is not None
    assert "Carr" in paper.authors
    assert paper.year == 2009
    assert paper.category == "volatility_dynamics"

    vol_papers = get_papers_by_category("volatility_dynamics")
    assert len(vol_papers) >= 2

    unknown = get_paper_by_id("UNKNOWN-PAPER")
    assert unknown is None


def test_all_papers_have_valid_latex_and_subsystems():
    """Verify that every academic paper has LaTeX mathematical equations and file links."""
    for p in RESEARCH_BIBLIOGRAPHY:
        assert p.title
        assert p.authors
        assert p.year > 1900
        assert p.latex_formula.startswith("\\") or "$" in p.latex_formula or "_" in p.latex_formula or r"\text" in p.latex_formula
        assert "src/volagent/" in p.volagent_subsystem
        assert p.relevance_to_track_2
