"""Species compilation deck: every author's account of one species (text pages, verbatim text + English
translation, figures), one .pptx + .pdf per species, for browsing without opening each paper.

Data: 08_知识库/结构化/{treatment,name_usage,work}.csv (+ figure.csv if present); PDF paths from work.csv local_path.
Marphysa version (adapted from P:/Travisia/03_脚本/85): text = OCR / text layer auto-cut by script 03 (not proofread;
page images are the authority); no translation yet.
Included: accounts L1-L4 (L4 marked "reference only"); L5 (lists, keys, comparisons, compilations) only listed.
usage: python3 deck.py <项目目录> "Marphysa orientalis" [--no-open]   (批量: yzz.py compilation 04)
output: 11_物种图文汇编/<Genus_species>/<Genus_species>_accounts_<date>.pptx/.pdf
"""
import csv, datetime, io, re, sqlite3, subprocess, sys, unicodedata
import numpy as np
from pathlib import Path

import fitz  # PyMuPDF
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfg  # noqa: E402
import importlib.util
_spec = importlib.util.spec_from_file_location('enh', Path(__file__).with_name('enhance.py'))
ENH = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ENH)
_spec = importlib.util.spec_from_file_location('typeset', Path(__file__).with_name('typeset.py'))
TS = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(TS)   # reflow / headings / italics (script 88)
from PIL import Image
NO_ENH = '--no-enhance' in sys.argv


def is_scan(page):
    """page is a scanned image (one picture covering most of the page)"""
    area = page.rect.width * page.rect.height
    return any((i['bbox'][2] - i['bbox'][0]) * (i['bbox'][3] - i['bbox'][1]) > 0.6 * area for i in page.get_image_info())


def jpeg(a):
    b = io.BytesIO(); Image.fromarray(a).save(b, 'JPEG', quality=93); return b.getvalue()
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

ROOT = cfg.ROOT
SP = cfg.ARGS[0]
S = cfg.S
OUT = ROOT / '11_物种图文汇编' / SP.replace(' ', '_'); OUT.mkdir(parents=True, exist_ok=True)
STAMP = datetime.date.today().isoformat()
FONT, FONT_EA = 'Arial', 'SimSun'
GREY, DARK, ACCENT = RGBColor(0x59, 0x59, 0x59), RGBColor(0x1F, 0x1F, 0x1F), RGBColor(0x1F, 0x4E, 0x79)
LANG = {'de': 'German', 'fr': 'French', 'es': 'Spanish', 'pt': 'Portuguese', 'la': 'Latin', 'ru': 'Russian',
        'zh': 'Chinese', 'ja': 'Japanese', 'it': 'Italian', 'sv': 'Swedish', 'da': 'Danish', 'nl': 'Dutch', 'en': 'English'}
LEVEL = {'L1': 'type re-examination', 'L2': 'type re-examination', 'L3': 'original description',
         'L4': 'non-type material: reference only', 'L5': 'list / key / comparison / compilation'}


def rows(name):
    return [r for r in csv.DictReader(open(S / name, encoding='utf-8-sig'))]


T = [r for r in rows('treatment.csv') if r['taxon'] == SP]
if not T: sys.exit(f'no treatments for {SP} in treatment.csv: build them first (script 54 / agents)')
NU = [r for r in rows('name_usage.csv') if r['taxon'] == SP]
FIG = [r for r in rows('figure.csv') if r['taxon'] == SP and r['image_file']] if (S / 'figure.csv').exists() else []
W = {r['work_id']: r for r in rows('work.csv')}
kb = sqlite3.connect(cfg.KB)
wrow = kb.execute("select name, authority, status from worms_names where name=? order by status='accepted' desc", (SP,)).fetchone()
if not wrow:
    full = T[0].get('taxon_valid_full', SP); wrow = (SP, full[len(SP):].strip(), f'accepted (valid taxon outside the {cfg.GENUS} list)')


def year(r):
    m = re.search(r'(1[6-9]|20)\d\d', r['work_id']); return int(m.group()) if m else 9999


T.sort(key=year)


def pdf_of(work_id):
    p = W.get(work_id, {}).get('local_path', '')
    return Path(p) if p and Path(p).exists() else None


def norm(s):
    s = unicodedata.normalize('NFKD', s).lower()
    return re.sub(r'[^a-z]', '', s)


def find_pages(pdf, text, n_probe=6):
    """PDF pages (0-based) whose text layer contains probes taken from the verbatim text."""
    doc = fitz.open(pdf); t = norm(text)
    probes = [t[i:i + 28] for i in range(0, max(len(t) - 28, 1), max(len(t) // n_probe, 28))][:n_probe]
    hits = []
    for p in range(len(doc)):
        pt = norm(doc[p].get_text())
        if any(pr and pr in pt for pr in probes): hits.append(p)
    return hits


def page_hint(pages):
    """'PDF 186-187', 'PDF 1-3, 4-6', 'PDF 26); 38 (PDF 50' -> 0-based page list"""
    out = []
    for grp in re.findall(r'PDF\s*((?:\d+\s*(?:[-–]\s*\d+)?\s*,?\s*)+)', pages):
        for a, b in re.findall(r'(\d+)(?:\s*[-–]\s*(\d+))?', grp):
            a = int(a); b = int(b) if b else a
            if b < a or b - a > 15: b = a
            out += list(range(a - 1, b))
    return out


def online_url(work_id):
    """DOI if known, else BHL/online link recorded in WoRMS sources, else WoRMS source page."""
    doi = W.get(work_id, {}).get('doi', '')
    m = re.search(r'10\.\d{4,}/\S+', doi)
    return 'https://doi.org/' + m.group().rstrip('.,;)') if m else ''


def local_uri(pdf, page=None):
    w = str(pdf).replace('/mnt/p/', 'P:/').replace('/mnt/n/', 'N:/')
    return 'file:///' + w + (f'#page={page}' if page else '')


def link(slide, x, y, w, h, label, url, size=12):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); box.text_frame.word_wrap = True
    r = box.text_frame.paragraphs[0].add_run(); r.text = label; r.font.size = Pt(size); r.font.name = FONT
    r.font.color.rgb = RGBColor(0x05, 0x63, 0xC1); r.font.underline = True; r.hyperlink.address = url
    return box


prs = Presentation(); prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
SW, SH = 13.333, 7.5


def tb(slide, x, y, w, h, text, size=12, bold=False, color=DARK, italic=False):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf = box.text_frame; tf.word_wrap = True
    for i, para in enumerate(text.split('\n')):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run(); r.text = para; f = r.font; f.size = Pt(size); f.bold = bold; f.italic = italic; f.name = FONT; f.color.rgb = color
        r._r.get_or_add_rPr().set('altLang', 'zh-CN')
        ea = r._r.get_or_add_rPr().makeelement('{http://schemas.openxmlformats.org/drawingml/2006/main}ea', {'typeface': FONT_EA})
        r._r.get_or_add_rPr().append(ea)
    return box


def rich(slide, x, y, w, h, page, size=12):
    """typeset paragraphs (script 88): left aligned, run-in headings bold, taxon names italic, page markers grey."""
    from pptx.enum.text import PP_ALIGN
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf = box.text_frame; tf.word_wrap = True
    for i, (para, cont) in enumerate(page):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT; p.line_spacing = 1.1; p.space_after = Pt(0 if cont else 5)
        marker = TS.PAGE_RE.fullmatch(para)
        for text, bold, italic in ([(para, False, False)] if marker else TS.runs(para)):
            r = p.add_run(); r.text = text; f = r.font; f.name = FONT; f.bold = bold; f.italic = italic
            f.size = Pt(size - 2 if marker else size); f.color.rgb = GREY if marker else DARK
            r._r.get_or_add_rPr().set('altLang', 'zh-CN')
            r._r.get_or_add_rPr().append(r._r.get_or_add_rPr().makeelement('{http://schemas.openxmlformats.org/drawingml/2006/main}ea', {'typeface': FONT_EA}))
    return box


def header(slide, title, sub='', url=None, label=None):
    tb(slide, 0.4, 0.2, 12.5, 0.6, title, 22, True, ACCENT)
    if sub: tb(slide, 0.4, 0.8, 12.5, 0.4, sub if len(sub) <= 150 else sub[:147] + '...', 12, False, GREY)
    tb(slide, 0.4, 7.05, 8.4, 0.3, f'{SP} — compilation of accounts by author — {STAMP}', 9, False, GREY)
    if url: link(slide, 9.0, 7.02, 4.0, 0.3, label or 'open source', url, 10)


def table(slide, data, x, y, w, colw, size=10):
    nr, nc = len(data), len(data[0])
    shp = slide.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(0.3 * nr)).table
    for j, cw in enumerate(colw): shp.columns[j].width = Inches(cw)
    for i, r in enumerate(data):
        for j, v in enumerate(r):
            cell = shp.cell(i, j); cell.text = str(v)
            for p in cell.text_frame.paragraphs:
                for run in p.runs: run.font.size = Pt(size); run.font.name = FONT; run.font.bold = (i == 0)


def chunks(text, n):
    """split text into n parts at sentence boundaries, roughly equal."""
    if n <= 1: return [text.strip()]
    sents = re.split(r'(?<=[.;:!?])\s+', text.strip()); target = len(text) / n; out, cur = [], ''
    for s in sents:
        if cur and len(cur) + len(s) > target and len(out) < n - 1: out.append(cur.strip()); cur = ''
        cur += s + ' '
    out.append(cur.strip()); return out + [''] * (n - len(out))


def picture_fit(slide, img_bytes, x, y, w, h, wpx, hpx):
    r = min(w / wpx, h / hpx); pw, ph = wpx * r, hpx * r
    slide.shapes.add_picture(io.BytesIO(img_bytes), Inches(x + (w - pw) / 2), Inches(y + (h - ph) / 2), Inches(pw), Inches(ph))


# 1 cover
s = prs.slides.add_slide(BLANK)
inc = [t for t in T if t['level'][:2] in ('L1', 'L2', 'L3', 'L4')]
box = tb(s, 0.8, 1.5, 11.7, 1.2, f'{wrow[0]} {wrow[1]}', 40 if len(f'{wrow[0]} {wrow[1]}') <= 36 else 34, True, ACCENT)
from pptx.enum.text import MSO_AUTO_SIZE
box.text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
_p = box.text_frame.add_paragraph(); _r = _p.add_run(); _r.text = f'WoRMS status: {wrow[2]}'; _r.font.size = Pt(18); _r.font.color.rgb = GREY; _r.font.name = FONT
_p.space_before = Pt(14)
_p = box.text_frame.add_paragraph(); _p.space_before = Pt(24); _r = _p.add_run(); _r.font.size = Pt(14); _r.font.name = FONT; _r.font.color.rgb = DARK
_r.text = (f'Accounts by author, with text page images and OCR text (auto-cut, not proofread; page images are the authority).\n'
   f'{len(inc)} accounts shown in full (L1-L4); {len(T) - len(inc)} lists / keys / comparisons (L5) listed only.\n'
   f'Built {STAMP} by script 85 from the structured layer (treatment, name_usage, work).')

# 2 synonymy / name usages
if NU:
    per = 14
    for k in range(0, len(NU), per):
        s = prs.slides.add_slide(BLANK); header(s, 'Synonymy and name usages', 'name as printed, work, pages, usage')
        data = [['Name as printed', 'Work', 'Pages', 'Figures', 'Usage', 'Note']] + [
            [u['name_as_printed'], u['work_id'], u['pages'], u['figures'], u['usage_type'][:70], u['taxon_concept_note'][:90]] for u in NU[k:k + per]]
        table(s, data, 0.4, 1.3, 12.5, [2.0, 1.5, 1.0, 1.2, 3.1, 3.7], 9)

# 3 list of accounts
s = prs.slides.add_slide(BLANK); header(s, 'Accounts in chronological order', 'L1/L2 type re-examination; L3 original description; L4 non-type material (reference only); L5 listed only')
data = [['Year', 'Work', 'Pages', 'Kind', 'Level', 'In this deck', 'File (literature folder)']]
for t in T:
    p = pdf_of(t['work_id'])
    data.append([year(t), t['work_id'], t['pages'][:22], t['kind'][:60], t['level'], 'yes' if t in inc else 'listed only', p.name[:55] if p else '(not a PDF / not held)'])
table(s, data, 0.4, 1.3, 12.5, [0.6, 1.6, 1.3, 3.6, 0.6, 1.0, 3.8], 8)

# 4 each account
missing = []
TSLOG = []
shown_pages, shown_figs = {}, set()
for t in inc:
    w = W.get(t['work_id'], {}); pdf = pdf_of(t['work_id'])
    s = prs.slides.add_slide(BLANK)
    tb(s, 0.8, 1.6, 11.7, 0.9, f"{w.get('author_short', t['work_id'])} {year(t)}", 34, True, ACCENT)
    meta = [f"Citation: {w.get('citation', '')}", f"Pages: {t['pages']}", f"Kind: {t['kind']}",
            f"Level: {t['level']} ({LEVEL.get(t['level'][:2], '')})", f"Material: {t['material']}",
            f"Language: {LANG.get(t['language'], t['language'])}", f"Figures: {t['figures'] or 'none'}",
            f"File (literature folder): {pdf.parent.name + '/' + pdf.name if pdf else 'not held'}"]
    tb(s, 0.8, 2.6, 11.7, 4.2, '\n'.join(meta), 14, False, DARK)
    url = online_url(t['work_id'])
    pages = (page_hint(t['pages']) or find_pages(pdf, t['original_text'])) if pdf else []
    if url: link(s, 0.8, 6.45, 11.7, 0.35, f'Online source: {url}', url, 12)
    if pdf: link(s, 0.8, 6.85, 11.7, 0.35, f'Open local PDF at page {pages[0] + 1}' if pages else 'Open local PDF', local_uri(pdf, pages[0] + 1 if pages else None), 12)
    # page images
    if pdf:
        if not pages: missing.append(f"{t['work_id']}: text pages not located in {pdf.name}")
        doc = fitz.open(pdf)
        doc = fitz.open(pdf)
        bad = [p for p in pages if not 0 <= p < len(doc)]
        if bad: missing.append(f"{t['work_id']}: page(s) {[b + 1 for b in bad]} not in {pdf.name} ({len(doc)} pages; portfolio/embedded file?)")
        pages = sorted(set(p for p in pages if 0 <= p < len(doc)))[:12]
        prev = shown_pages.setdefault(t['work_id'], set())
        if pages and set(pages) <= prev:
            s = prs.slides.add_slide(BLANK); header(s, f"{w.get('author_short', t['work_id'])} {year(t)} — text pages", 'same pages as shown above for this work')
            tb(s, 0.4, 1.5, 12.5, 1.0, f"PDF page(s) {', '.join(str(p + 1) for p in pages)}: shown in the previous section of this work.", 14)
            link(s, 0.4, 2.6, 6, 0.4, f'open PDF page {pages[0] + 1}', local_uri(pdf, pages[0] + 1), 12)
            pages = []
        prev.update(pages)
        for k, p in enumerate(pages, 1):
            enh = is_scan(doc[p]) and not NO_ENH
            if enh:   # native scan resolution + background flattening / contrast (script 87); no content added
                g, dpi = ENH.render_page(doc[p], max_px=5000)
                a = ENH.enhance(g, 'figure' if (g < 100).mean() > 0.20 else 'text', dpi=dpi)
                img, iw, ih = jpeg(a), a.shape[1], a.shape[0]
            else:
                dpi = int(min(300, 6000 * 72 / max(doc[p].rect.width, doc[p].rect.height)))  # very large pages: cap at 6000 px
                pix = doc[p].get_pixmap(dpi=dpi); img, iw, ih = pix.tobytes('jpeg', jpg_quality=95), pix.width, pix.height
            parts = [(img, iw, ih, '')]
            if iw > 1.25 * ih:   # two-page spread: one half per slide for maximum size
                src = a if enh else np.array(Image.open(io.BytesIO(img)).convert('L'))
                h2 = src.shape[1] // 2
                parts = [(jpeg(src[:, :h2 + 20]), h2 + 20, ih, ' (left half)'), (jpeg(src[:, h2 - 20:]), src.shape[1] - h2 + 20, ih, ' (right half)')]
            for img, iw, ih, half in parts:
              s = prs.slides.add_slide(BLANK)
              r = min(9.2 / iw, 7.3 / ih); pw, ph = iw * r, ih * r
              s.shapes.add_picture(io.BytesIO(img), Inches(0.1), Inches(0.1), Inches(pw), Inches(ph))
              px = 0.1 + pw + 0.3; pwid = SW - px - 0.3
              tb(s, px, 0.4, pwid, 1.2, f"{w.get('author_short', t['work_id'])} {year(t)}", 24, True, ACCENT)
              tb(s, px, 1.6, pwid, 3.6, f"Text page {k} of {len(pages)}{half}\nPDF page {p + 1}\nPrinted pages: {t['pages']}\n\nFile:\n{pdf.name}", 12, False, DARK)
              if enh: tb(s, px, 4.9, pwid, 0.5, f'Scan enhanced ({dpi} dpi; background flattened, contrast stretched; no content added). Original: link below.', 9, False, GREY, italic=True)
              link(s, px, 5.4, pwid, 0.4, f'open PDF page {p + 1}', local_uri(pdf, p + 1), 12)
              tb(s, px, 6.6, pwid, 0.7, f'{SP}\ncompilation of accounts by author — {STAMP}', 9, False, GREY)
    # verbatim text + translation
    orig, tr = t['original_text'].strip(), t['translation_en'].strip()
    two = t['language'] != 'en' and tr
    po = TS.reflow(orig, TSLOG); TS.verify(orig, po); pt_ = TS.reflow(tr, TSLOG) if two else []
    if two: TS.verify(tr, pt_)
    kw = dict(width_in=6.1, height_in=5.4, size=11) if two else dict(width_in=12.5, height_in=5.6, size=12)
    n = max(len(TS.paginate(po, **kw)[0]), len(TS.paginate(pt_, **kw)[0]) if two else 0)
    if two:   # both columns on the same number of slides, balanced
        pa, pb = TS.paginate(po, n if n > 1 else None, **kw)[0], TS.paginate(pt_, n if n > 1 else None, **kw)[0]
    else:     # fill each slide
        pa = TS.paginate(po, **kw)[0]; pb = [[]] * len(pa)
    n = len(pa)
    for i, (a, b) in enumerate(zip(pa, pb), 1):
        s = prs.slides.add_slide(BLANK)
        header(s, f"{w.get('author_short', t['work_id'])} {year(t)} — text" + (f' ({i}/{n})' if n > 1 else ''), f"pages {t['pages']}; OCR / text layer, {LANG.get(t['language'], t['language'])}" + ('; English translation right' if two else '') + '; line breaks reflowed; not proofread')
        if two:
            tb(s, 0.4, 1.25, 6.1, 0.3, f"Original ({LANG.get(t['language'], t['language'])})", 11, True, GREY)
            rich(s, 0.4, 1.55, 6.1, 5.4, a, 11)
            tb(s, 6.85, 1.25, 6.1, 0.3, 'English translation', 11, True, GREY)
            rich(s, 6.85, 1.55, 6.1, 5.4, b, 11)
        else:
            rich(s, 0.4, 1.3, 12.5, 5.6, a, 12)
    if t['text_note']: tb(s, 0.4, 6.7, 12.5, 0.35, f"Note: {t['text_note'][:220]}", 9, False, GREY, italic=True)
    # figures
    figs = [f for f in FIG if f['work_id'] == t['work_id'] and f['fig_id'] not in shown_figs]; shown_figs.update(f['fig_id'] for f in figs)
    for f in figs:
        img = ROOT / f['image_file']
        if not img.exists(): missing.append(f"figure image missing: {f['image_file']}"); continue
        data = img.read_bytes(); pm = fitz.Pixmap(str(img)); s = prs.slides.add_slide(BLANK)
        fenh = False
        if pdf and f['pdf_page'].isdigit() and not NO_ENH and int(f['pdf_page']) <= len(fitz.open(pdf)) and is_scan(fitz.open(pdf)[int(f['pdf_page']) - 1]):
            g = np.array(Image.open(img).convert('L')); a = ENH.enhance(g, 'figure', dpi=300)
            data, fenh = jpeg(a), True
        fu = local_uri(pdf, int(f['pdf_page'])) if pdf and f['pdf_page'].isdigit() else None
        header(s, f"{w.get('author_short', t['work_id'])} {year(t)} — {f['label']}", f"{f['depicts']}; magnification {f['magnification'] or 'not stated'}; PDF page {f['pdf_page']}", fu, f"open PDF page {f['pdf_page']}")
        picture_fit(s, data, 0.4, 1.25, 12.5, 5.4, pm.width, pm.height)
        if fenh: tb(s, 0.4, 6.95 - 0.3, 6, 0.3, 'Scan enhanced (contrast only; no content added)', 8, False, GREY, italic=True)
        if f['note']: tb(s, 0.4, 6.7, 12.5, 0.35, f"Note: {f['note'][:220]}", 9, False, GREY, italic=True)

# L5 listed
l5 = [t for t in T if t not in inc]
if l5:
    s = prs.slides.add_slide(BLANK); header(s, 'Lists, keys, comparisons, compilations (L5): listed only', 'not evidence; text kept in the structured layer (treatment.csv)')
    table(s, [['Year', 'Work', 'Pages', 'Kind']] + [[year(t), t['work_id'], t['pages'][:30], t['kind'][:90]] for t in l5], 0.4, 1.3, 12.5, [0.8, 2.2, 2.5, 7.0], 10)

stem = OUT / f"{SP.replace(' ', '_')}_accounts_{STAMP}"
pptx = stem.with_suffix('.pptx')
for k in range(2, 20):
    try: prs.save(pptx); break
    except PermissionError: pptx = pptx.with_name(f'{stem.name}_v{k}.pptx')
PDF_OPTS = 'pdf:impress_pdf_Export:{"ReduceImageResolution":{"type":"boolean","value":"false"},"Quality":{"type":"long","value":"95"}}'
subprocess.run(['soffice', '--headless', '--convert-to', PDF_OPTS, '--outdir', str(OUT), str(pptx)], capture_output=True, timeout=600)
# LibreOffice writes local links as broken relative paths: rewrite them relative to the deck (survive folder moves)
import os, urllib.parse
pdfout = pptx.with_suffix('.pdf'); d = fitz.open(pdfout); fixed = 0
for pg in d:
    for L in pg.get_links():
        if L.get('kind') == fitz.LINK_GOTOR and L.get('file'):
            name = urllib.parse.unquote(L['file']).split(cfg.WIN)[-1]
            rel = os.path.relpath(ROOT / name, OUT).replace(os.sep, '/'); L['file'] = rel
            try:
                pg.update_link(L)
            except Exception:   # 文件名含括号/特殊字符时 update_link 生成非法字典 (2026-11-08 gravelyi, mossambica): 直接写 Filespec
                d.xref_set_key(L['xref'], 'A/F', f"<</Type/Filespec/F <{rel.encode('utf-8').hex()}>/UF <FEFF{rel.encode('utf-16-be').hex().upper()}>>>")
            fixed += 1
    for L in pg.get_links():   # /UF must be a UTF-16 text string so Acrobat reads the non-ASCII folder name
        if L.get('kind') == fitz.LINK_GOTOR:
            rel = urllib.parse.unquote(L['file']); hx = '<FEFF' + rel.encode('utf-16-be').hex().upper() + '>'
            d.xref_set_key(L['xref'], 'A/F/UF', hx)
d.saveIncr() if d.can_save_incrementally() else (d.save(str(pdfout) + '.tmp'), os.replace(str(pdfout) + '.tmp', pdfout))
d.close()
print(pptx.relative_to(ROOT), '| slides', len(prs.slides), '| pdf', pptx.with_suffix('.pdf').exists()), '| local links', fixed
for m in missing: print('CHECK:', m)
for m in TSLOG: print('TYPESET:', m)
if '--no-open' not in sys.argv:
    win = subprocess.run(['wslpath', '-w', str(pptx.with_suffix('.pdf'))], capture_output=True, text=True).stdout.strip()
    subprocess.run(['cmd.exe', '/c', 'start', '', win], capture_output=True)
