"""Typeset verbatim text for the species compilation deck (script 85).

Only whitespace is changed: hard PDF line breaks are reflowed into paragraphs, end-of-line hyphens
are resolved, run-in headings are made bold and taxon names italic. verify() proves the text is
unchanged (all characters except whitespace and resolved line-end hyphens).

Rules
- paragraph break: before a page marker "[p. N]", before a known heading at line start, or after a
  short line (< 60 % of the typical line length) that is followed by a capitalised line.
- line-end hyphen: lowercase-hyphen + lowercase -> soft hyphen removed if the joined word occurs
  elsewhere in the corpus, kept if the hyphenated word does, otherwise removed and listed as
  uncertain; any other hyphen/dash (MSL-|EG, 979A-|41DB, 8–|11) kept, line joined without space.
usage (test): python3 typeset.py <项目目录> "Marphysa orientalis"
"""
import csv, re, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfg  # noqa: E402
ROOT = cfg.ROOT
S = cfg.S

HEADINGS = ['Material examined', 'Type material', 'Non-type material', 'Additional material', 'Other material',
            'Material', 'Holotype', 'Paratypes', 'Paratype', 'Syntypes', 'Lectotype', 'Neotype',
            'Diagnosis', 'Emended diagnosis', 'Description', 'Redescription', 'Remarks', 'Etymology',
            'Type locality', 'Type-locality', 'Distribution', 'Habitat', 'Comparison', 'Comparisons',
            'Variation', 'Biology', 'Ecology', 'Distribution, ecology', 'Distribution and ecology', 'Distribution and habitat', 'Molecular data', 'Synonymy', 'Colour', 'Color',
            # de / fr / es / pt / la
            'Fundort', 'Fundorte', 'Beschreibung', 'Bemerkungen', 'Verbreitung',
            'Matériel examiné', 'Remarques', 'Répartition', 'Localité type',
            'Material examinado', 'Descripción', 'Descrição', 'Observaciones', 'Comentários', 'Observações',
            'Distribución', 'Distribuição', 'Etimología', 'Etimologia', 'Diagnose', 'Diagnosis latina']
HEAD_RE = re.compile(r'^(' + '|'.join(sorted((re.escape(h).replace(r'\ ', r'[\s ]+').replace(r'\-', r'[-\s ]+')
                                               for h in HEADINGS), key=len, reverse=True)) + r')([.:]|\s[—–-])', re.I)
MID_HEAD = None  # set below
PAGE_RE = re.compile(r'\[\s*(?:(?:printed|orig\.?|original)\s+)?(?:p{1,2}\.\s*[^\]]{1,20}|(?:Legend|Figure|Figs?\.?|Plate|Table|Continued|End)\b[^\]]{0,150})\]')
MID_HEAD = re.compile(r'(?<=[.)\]])[ \u00a0]+(?=(?:' + '|'.join(re.escape(h) for h in sorted(HEADINGS, key=len, reverse=True) if h[0].isupper()) + r')[.:] )')
CONJ = {'und', 'oder', 'bis', 'and', 'or', 'to', 'et', 'ou', 'e', 'y', 'o', 'a'}
KEEP = {'shaped', 'like', 'type', 'formed', 'bearing', 'sized', 'walled', 'developed', 'defined', 'tipped', 'lobed'}
DASH_END = re.compile(r'[-‐‑–—]$')


def _corpus():
    words = set()
    for name in ('treatment.csv',):
        for r in csv.DictReader(open(S / name, encoding='utf-8-sig')):
            words.update(w.lower() for w in re.findall(r"[^\W\d_]+(?:-[^\W\d_]+)*", r['original_text'].replace('-\n', '#')))
    return words


def _names():
    """genera and epithets for italics, from name usages + WoRMS list."""
    gen, epi = set(cfg.GENERA) | {'Travisia'}, set()
    for r in csv.DictReader(open(S / 'name_usage.csv', encoding='utf-8-sig')):
        for n in (r.get('name_as_printed', ''), r.get('taxon', '')):
            p = re.findall(r'[A-Za-z]+', n)
            if len(p) >= 2 and p[0][0].isupper() and p[1].islower(): gen.add(p[0]); epi.add(p[1])
    try:
        import sqlite3
        for (n,) in sqlite3.connect(cfg.KB).execute('select name from worms_names'):
            p = n.split()
            if len(p) >= 2: gen.add(p[0]); epi.add(p[1])
    except Exception:
        pass
    gen = {g for g in gen if len(g) >= 4 and g.isalpha()} - {'Kesun', 'Riben'}   # drop abbreviations, pinyin
    epi = {e for e in epi if len(e) >= 3} - {'nov', 'spp', 'and', 'des', 'near', 'chou', 'haiyong'}
    return gen, epi


_CORPUS = None
_NAMES = None


def name_regex():
    global _NAMES
    if _NAMES is None:
        gen, epi = _names()
        g = '|'.join(sorted(gen, key=len, reverse=True)); e = '|'.join(sorted(epi, key=len, reverse=True))
        gi = '|'.join(sorted({x[0] + r'\.' for x in gen} | {x[:2] + r'\.' for x in gen}, key=len, reverse=True))   # T. / Tr.
        _NAMES = re.compile(rf'\b(?:(?:{g})\b(?:[\s ]+(?:\((?:{g})\)[\s ]+)?(?:{e})\b(?:[\s ]+(?:{e})\b)?)?|(?:{gi})[\s ]*(?:{e})\b)')
    return _NAMES


def _join_hyphen(left, right, log):
    """left ends with a dash; return joined string."""
    global _CORPUS
    m1 = re.search(r'([^\W\d_]+)-$', left); m2 = re.match(r'([^\W\d_]+)', right)
    if left.endswith('-') and m1 and m2 and m1.group(1)[-1].islower() and m2.group(1)[0].islower():
        if _CORPUS is None: _CORPUS = _corpus()
        a, b = m1.group(1), m2.group(1); joined, hyph = (a + b).lower(), (a + '-' + b).lower()
        if b in CONJ: return left + ' ' + right            # suspended hyphen: "Mund- und Seitenteile"
        if b in KEEP: return left + right                  # compound: "bead-shaped", "club-like"
        if joined in _CORPUS: return left[:-1] + right
        if hyph in _CORPUS: return left + right
        log.append(f'uncertain hyphen: {a}-|{b} -> {a}{b}')
        return left[:-1] + right
    return left + right


def reflow(text, log=None):
    """verbatim text -> list of paragraphs (strings); page markers become their own paragraphs."""
    log = [] if log is None else log
    text = text.replace('\r', '')
    text = PAGE_RE.sub(lambda m: '\n' + m.group(0) + '\n', text)
    text = MID_HEAD.sub('\n', text)
    lines = [re.sub(r'[ \t]+', ' ', re.sub(r' \s+|\s+ ', ' ', l)).strip() for l in text.split('\n')]
    body = [len(l) for l in lines if len(l) > 20]
    typical = statistics.median(body) if body else 80
    paras, cur, prev = [], '', ''
    for l in lines:
        if not l:
            if cur: paras.append(cur); cur = ''
            prev = ''; continue
        page = PAGE_RE.fullmatch(l)
        brk = (page or HEAD_RE.match(l) or PAGE_RE.fullmatch(prev or 'x')
               or (prev and len(prev) < 0.6 * typical and l[0].isupper()))
        if not cur:
            cur = l
        elif brk:
            paras.append(cur); cur = l
        elif DASH_END.search(cur):
            cur = _join_hyphen(cur, l, log)
        else:
            cur = cur + ' ' + l
        prev = l
        if page: paras.append(cur); cur = ''
    if cur: paras.append(cur)
    return paras


def runs(para):
    """paragraph -> [(text, bold, italic)]: run-in heading bold, taxon names italic."""
    out, pos = [], 0
    m = HEAD_RE.match(para)
    if m: out.append((m.group(0), True, False)); pos = m.end()
    rest = para[pos:]
    k = 0
    for n in name_regex().finditer(rest):
        if n.start() > k: out.append((rest[k:n.start()], False, False))
        out.append((n.group(0), False, True)); k = n.end()
    if k < len(rest): out.append((rest[k:], False, False))
    return out


def _key(s):
    return re.sub(r'[\s ­\-‐‑]', '', s)


def verify(original, paras):
    a, b = _key(original), _key(''.join(paras))
    if a != b:
        i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        raise ValueError(f'typeset text differs from verbatim at char {i}: {a[i - 30:i + 30]!r} vs {b[i - 30:i + 30]!r}')


def _lines(p, chars_per_line):
    return max(1, -(-len(p) // chars_per_line))


def paginate(paras, n_pages=None, width_in=12.5, height_in=5.6, size=12, spacing=1.1, after_pt=5):
    """paragraphs -> pages (lists of paragraphs). Long paragraphs split at '; ' or sentence ends.
    With n_pages: split into exactly that many pages of roughly equal height."""
    cpl = int(width_in * 72 / (size * 0.50))           # Arial average glyph ~0.50 em
    line_h = size * 1.2 * spacing
    cap = int(height_in * 72 / line_h) - 1               # usable lines per page

    def cost(p): return _lines(p, cpl) + after_pt / line_h

    pieces = []                                          # split paragraphs longer than one page
    for i, p in enumerate(paras):
        if _lines(p, cpl) <= cap * 0.9: pieces.append((p, False)); continue
        parts = re.split(r'(?<=;)\s|(?<=[.!?])\s(?=[A-Z])', p); cur = ''
        for s in parts:
            if cur and _lines(cur + ' ' + s, cpl) > cap * 0.9: pieces.append((cur, True)); cur = s
            else: cur = (cur + ' ' + s) if cur else s
        pieces.append((cur, False))
    total = sum(cost(p) for p, _ in pieces)
    target = cap if n_pages is None else max(total / n_pages, 1)
    pages, cur, h = [], [], 0.0
    for p, cont in pieces:
        c = cost(p)
        if cur and h + c > target + 0.5 and (n_pages is None or len(pages) < n_pages - 1) and h + c > 0:
            pages.append(cur); cur, h = [], 0.0
        cur.append((p, cont)); h += c
    if cur: pages.append(cur)
    if n_pages:
        pages += [[] for _ in range(n_pages - len(pages))]
    return pages, cap


if __name__ == '__main__':
    sp = cfg.ARGS[0] if cfg.ARGS else 'Marphysa orientalis'
    for r in csv.DictReader(open(S / 'treatment.csv', encoding='utf-8-sig')):
        if r['taxon'] != sp: continue
        log = []; ps = reflow(r['original_text'], log); verify(r['original_text'], ps)
        pages, cap = paginate(ps)
        print(f"== {r['work_id']} {r['language']} paras {len(ps)} pages {len(pages)}", *log, sep='\n  ')
        for p in ps[:6]: print('  |', p[:140])
