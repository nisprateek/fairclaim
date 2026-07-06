"""Deterministic output-safety guardrail: citation integrity.

Confirmed live during Day-1 testing: the T&C analysis agent cited "s.28" for
a delivery clause — real Consumer Rights Act 2015 content from the model's
own training knowledge, not something backend/knowledge/CRA_2015_KB.md
covers or a tool returned. Prompting alone ("cite the section you used")
doesn't reliably stop a model from reaching into its own background
knowledge for a citation. This after_agent_callback deterministically strips
any statutory citation outside our curated, reviewed set once the agent's
turn completes, so the tool only ever vouches for sections it actually
reviewed — never a plausible-sounding invented (or merely uncurated) one.
"""

from __future__ import annotations

import re

from fairclaim.backend.mcp_server.server import STATUTORY_STANDARDS

_KNOWN_SECTIONS = set(STATUTORY_STANDARDS.keys())

# Confirmed live: the model sometimes puts the *full statutory text* returned
# by get_statutory_standard into statutory_basis instead of a short code
# ("s.9: Satisfactory quality — goods must meet..." instead of "s.9"). An
# exact-match normalize wrongly treats that as an uncurated citation and
# strips a perfectly legitimate one. Extract just the leading section number
# from anywhere in the string instead of assuming the whole string is a code.
_SECTION_PATTERN = re.compile(r"s\.?\s*(\d+[a-z]?)", re.I)


def _normalize_section(section: str) -> str | None:
    match = _SECTION_PATTERN.search(section)
    return f"s.{match.group(1).lower()}" if match else None


def _short_label(section: str) -> str:
    """Short display form for a dropped citation — never dump a long string
    (e.g. full statutory text mistakenly placed in statutory_basis) into the
    user-facing note."""
    normalized = _normalize_section(section)
    if normalized:
        return normalized
    return section if len(section) <= 24 else f"{section[:24]}…"


def _scrub(item: dict) -> None:
    basis = item.get("statutory_basis") or []
    kept, dropped = [], []
    for s in basis:
        normalized = _normalize_section(s)
        # Keep the citation in its own normalized short form if curated — even
        # if the model padded it with the full statutory text, s.9 is still s.9.
        (kept.append(normalized) if normalized in _KNOWN_SECTIONS else dropped.append(s))
    # Always write back — even when nothing was dropped, `kept` may still
    # differ from `basis` (e.g. long-form text normalized down to "s.9").
    item["statutory_basis"] = kept
    if not dropped:
        return
    # The dropped-citation note is legal detail, so it belongs in the legal
    # explanation — every scrubbed model (ClauseVerdict, RemedyResult) has one.
    item["legal_explanation"] = item.get("legal_explanation", "") + (
        f" [Note: citation(s) {', '.join(_short_label(s) for s in dropped)} removed — outside "
        "this tool's curated statutory set; verify against legislation.gov.uk before relying on them.]"
    )


def make_citation_guard(state_key: str, list_field: str | None = None):
    """Build an after_agent_callback that scrubs uncurated citations from
    session state under `state_key` — from each item in `list_field` if the
    result is a list of sub-items (e.g. "clauses"), otherwise the result itself.
    """

    def guard(callback_context):
        result = callback_context.state.get(state_key)
        if not result:
            return None
        if list_field:
            for item in result.get(list_field, []):
                _scrub(item)
        else:
            _scrub(result)
        callback_context.state[state_key] = result
        return None

    return guard
