"""Taxon-name typography: split a name into (text, italic) runs following name_style.json.

Rules (ICZN/ICN convention, as used in taxonomic figures):
- genus, subgenus "(Neanthes)", species and subspecies epithets, abbreviated genus "M." -> italic
- ranks above genus (Eunicidae, Nereidinae, Eunicida...) -> whole name upright, e.g. "Eunicidae und."
- qualifiers sp. / spp. / cf. / aff. / var. / subsp. / und. ... -> upright
- everything after sp. / gen. / isolate / environmental ... -> upright (informal codes "sp. E HA-2019", "BOLD:AAY5846")
- tokens with digits, all-caps codes, ':' or '_' -> upright
- author citation (capitalised word or "(" after the epithet) -> upright to the end: "M. sanguinea (Montagu, 1813)"
Modes: auto (rules above) | all (whole label italic) | none (whole label upright).

  python3 taxname.py "Marphysa cf. sp. E GK-2025"     # prints the runs (debug; compare with molheat.R --print-labels)
"""
import json
import re
import sys
from pathlib import Path

STYLE = json.loads((Path(__file__).with_name("name_style.json")).read_text(encoding="utf-8"))
_UP = {t.lower() for t in STYLE["upright_tokens"]}
_REST = {t.lower() for t in STYLE["rest_upright_after"]}
_RX = [re.compile(r) for r in STYLE["upright_regex"]]


def is_higher_taxon(word):
    w = word.strip("()[],")
    return w in STYLE["higher_taxa"] or any(w.endswith(s) and w[:1].isupper() for s in STYLE["higher_rank_suffixes"])


def token_flags(name):
    """-> list of (token, italic) for each whitespace token."""
    toks = name.split()
    if not toks:
        return []
    if is_higher_taxon(toks[0]):
        return [(t, False) for t in toks]
    out, rest_up = [], False
    for i, t in enumerate(toks):
        low = t.lower()
        if rest_up:
            out.append((t, False))
            continue
        if i == 1 and re.fullmatch(r"\([A-Z][a-z]+\)", t):            # subgenus
            out.append((t, True))
            continue
        if i >= 1 and (t[:1].isupper() or t.startswith("(")) and low not in _UP:   # author citation
            rest_up = True
            out.append((t, False))
            continue
        up = low in _UP or any(r.search(t) for r in _RX)
        if low in _REST:
            rest_up = True
        out.append((t, not up))
    return out


def segments(name, mode="auto"):
    """-> list of (text, italic) runs, adjacent tokens of same style merged, spaces kept."""
    name = " ".join(str(name).split())
    if mode == "all":
        return [(name, True)]
    if mode == "none":
        return [(name, False)]
    runs = []
    for i, (t, it) in enumerate(token_flags(name)):
        sep = " " if i else ""
        if runs and runs[-1][1] == it:
            runs[-1] = (runs[-1][0] + sep + t, it)
        elif runs:                     # style change: space stays with the previous run
            runs[-1] = (runs[-1][0] + sep, runs[-1][1])
            runs.append((t, it))
        else:
            runs.append((t, it))
    return runs


def abbreviate(name):
    """'Marphysa aegypti' -> 'M. aegypti'; 'Marphysa sp.' and higher taxa unchanged."""
    toks = name.split()
    if len(toks) < 2 or is_higher_taxon(toks[0]) or toks[1].lower() in ("sp.", "spp.", "sp", "spp"):
        return name
    if re.fullmatch(r"[A-Z][a-z]+", toks[0]):
        return f"{toks[0][0]}. " + " ".join(toks[1:])
    return name


if __name__ == "__main__":
    for n in sys.argv[1:]:
        print(n, "=>", " | ".join(f"{'I' if it else 'R'}:{t!r}" for t, it in segments(n)))
