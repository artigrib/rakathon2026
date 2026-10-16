"""Repair Czech diacritics lost in export ('_' and U+FFFD in place of accented letters).

Strategy: broken characters are wildcards; match the whole value against a vocabulary of
known clean values of the same length. Unknown values are returned unchanged (and flagged).
"""
from __future__ import annotations

import re

BROKEN = re.compile(r"[_�]")
CODE = re.compile(r"^[A-Za-z0-9_\-]+$")  # snake_case codes like lung_screening_information are fine

VOCAB = [
    # regions
    "Hlavní město Praha", "Středočeský kraj", "Jihočeský kraj", "Plzeňský kraj", "Karlovarský kraj",
    "Ústecký kraj", "Liberecký kraj", "Královéhradecký kraj", "Pardubický kraj", "Vysočina",
    "Jihomoravský kraj", "Olomoucký kraj", "Zlínský kraj", "Moravskoslezský kraj",
    # smoking notes
    "Bývalý kuřák deset cigaret denně", "Bývalý kuřák jedna krabička denně",
    "Bývalý kuřák patnáct cigaret denně", "Kouří jednu krabičku denně",
    "Kouří přibližně dvě krabičky denně", "Kouří přibližně třicet cigaret denně",
    "Kuřácká anamnéza není dostupná", "Nikdy nekouřil", "Počet cigaret za den není uveden",
    "Dokumentace uvádí rozdílné hodnoty",
    # CT reports / referrals
    "Bez akutní patologie v dutině břišní.", "Bez akutní patologie.", "Bez akutních ložiskových změn.",
    "Bez akutních změn.", "Bez akutního nálezu.", "Bez akutního traumatu.", "Bez ložiskových změn.",
    "Bez suspektních ložisek.", "Bez známek akutního traumatu.", "Malý nespecifický uzlík k další kontrole.",
    "Stabilní nález bez akutních změn.", "Stabilní nález.",
    "CT hrudníku", "CT hrudníku pro chronický kašel", "CT hrudníku pro dušnost", "CT hrudníku pro kašel",
    "CT hrudníku pro bolesti na hrudi", "Kontrolní CT hrudníku", "CT břicha", "CT břicha pro bolesti břicha",
    "CT břicha pro anémii", "CT hlavy", "CT hlavy po pádu", "CT hlavy pro závratě",
    "CT hlavy pro poruchu rovnováhy", "CT hlavy pro bolesti hlavy", "LDCT hrudníku",
    "LDCT hrudníku v rámci kontroly", "Syntetická adresa 1 Praha",
]


def _pattern(broken: str) -> re.Pattern:
    return re.compile("^" + "".join("." if BROKEN.match(ch) else re.escape(ch) for ch in broken) + "$")


_cache: dict[str, str | None] = {}


def repair(value: str | None) -> tuple[str | None, bool]:
    """Returns (text, was_unrepairable)."""
    if not value or not BROKEN.search(value) or CODE.match(value):
        return value, False
    if value not in _cache:
        pat = _pattern(value)
        hits = [v for v in VOCAB if pat.match(v)]
        _cache[value] = hits[0] if len(hits) == 1 else None
    fixed = _cache[value]
    return (fixed, False) if fixed else (value, True)
