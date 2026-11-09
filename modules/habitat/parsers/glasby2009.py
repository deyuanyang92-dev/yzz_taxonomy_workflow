"""Parser for Glasby, Timm, Muir & Gil (2009) Catalogue of non-marine Polychaeta (Zootaxa 2070: 1-52).

Input: `pdftotext -layout` text of the full 52-page PDF.
Output: one dict per catalogue entry (species, species group, subspecies or informal 'sp.').

Entry layout in the catalogue:
    <Name (Author)>                    current name as used by Glasby et al.
    <Original combination, year>       0..n lines: original combination + listed synonyms
    Ecology: FW | FT | ST | T | CP ...
    Distribution: AT, PA, ...
    Habitat: LR, ES, ...
    Comments: ...                      optional, may wrap and cross page breaks
    Additional references: ...         optional
"""
import re

HEADER = re.compile(r"Zootaxa 2070 © 2009 Magnolia Press")
PAGE_FOOT = re.compile(r"Magnolia Press\s*·\s*(\d+)\s*$")    # odd pages:  '... Magnolia Press · 3'
PAGE_HEAD = re.compile(r"^\s*(\d+)\s*·\s*Zootaxa")             # even pages: '4 · Zootaxa 2070 ...'
FAMILY = re.compile(r"^([A-Z][A-Za-z]+idae)\s+[A-Z]|^(Family Unknown)\s*$")
CLADE = re.compile(r"^[A-Z]{4,}(?:\s+[A-Z]{4,})*\s*$")          # SCOLECIDA, ACICULATA ...
FIELD = re.compile(r"^(Ecology|Distribution|Habitat|Comments?|Additional references):\s*(.*)$")
KEYS = {"Ecology": "ecology", "Distribution": "distribution", "Habitat": "habitat", "Comment": "comments",
        "Comments": "comments", "Additional references": "additional_refs"}


def _lines(text):
    """Catalogue body lines with page numbers; page headers removed."""
    body = re.split(r"\n\s*Catalogue\s*\n", text, maxsplit=1)[1]
    body = re.split(r"\n\s*Acknowledgements\s*\n", body, maxsplit=1)[0]
    page, out = 3, []
    for raw in body.splitlines():
        m = PAGE_FOOT.search(raw) or PAGE_HEAD.search(raw)
        if HEADER.search(raw):
            page = int(m.group(1)) if m else page
            out.append((page, None))          # page break marker
            continue
        out.append((page, raw.rstrip()))
    return out


TAXON = re.compile(r"^[A-ZÆ][a-zæ]+(?: \([A-Z][a-z]+\))? (?:[a-z]+|sp\.|cf\.|nr\.|indet\.)(?:\s|$|,)")


def _headish(t):
    """Name/synonym line: taxon name, 'Non X sensu Y', or a name followed by an authority year."""
    return bool(TAXON.match(t) or t.startswith("Non ") or re.match(r"^[A-ZÆ][a-zæ]+ .*\b(1[789]|20)\d\d[a-z]?\b", t))


def parse(text):
    """Segment on 'Ecology:' lines; the entry head = taxon-name lines directly above it."""
    lines = [(pg, t.strip()) for pg, t in _lines(text) if t is not None]
    eco = [i for i, (_, t) in enumerate(lines) if t.startswith("Ecology:")]
    starts = []
    for i in eco:
        j = i
        while j - 1 >= 0 and not lines[j - 1][1]:          # page break between name and Ecology
            j -= 1
        k = j
        while j - 1 >= 0 and lines[j - 1][1] and not FIELD.match(lines[j - 1][1]) and _headish(lines[j - 1][1]):
            j -= 1
        if j == k:
            raise ValueError(f"no taxon name above Ecology line {i}: {lines[i - 1][1]!r}")
        starts.append(j)
    # family / clade context: last header line before each entry start
    rows = []
    for n, j in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        family = clade = ""
        for k in range(j - 1, -1, -1):
            t = lines[k][1]
            if not family and FAMILY.match(t):
                family = (FAMILY.match(t).group(1) or "Family Unknown").capitalize().replace("Family unknown", "Family Unknown")
            if CLADE.match(t):
                clade = t.title()
                break
        head, fields, key = [], {}, None
        for _, t in lines[j:end]:
            if not t:
                continue
            if FAMILY.match(t) or CLADE.match(t):
                break
            m = FIELD.match(t)
            if m:
                key = KEYS[m.group(1)]
                fields[key] = (fields.get(key, "") + " " + m.group(2)).strip()
            elif key:
                fields[key] = (fields[key] + " " + t).strip()
            else:
                head.append(t)
        if not TAXON.match(head[0]):
            raise ValueError(f"entry head is not a taxon name: {head[0]!r} (page {lines[j][0]})")
        name_line, others = head[0], head[1:]
        name = re.sub(r"\s+species group$", "", name_line)
        rows.append({
            "glasby_name": name,
            "species_group": "Y" if name_line.endswith("species group") else "",
            "listed_names": " | ".join(others),
            "original_combination": others[0] if others else "",
            "glasby_family": family,
            "glasby_clade": clade,
            "ecology": fields.get("ecology", ""),
            "distribution": fields.get("distribution", ""),
            "habitat": fields.get("habitat", ""),
            "comments": re.sub(r"(?<=[a-z])-\s+(?=[a-z])", "", fields.get("comments", "")),
            "additional_refs": fields.get("additional_refs", ""),
            "page": lines[j][0],
        })
    return rows
