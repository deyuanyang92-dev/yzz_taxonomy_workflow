"""04 物种页记录 (提取层): WoRMS taxdetails 页全部区块 + Type data / Descriptive notes 每一项 -> 两个 TSV

只照搬 WoRMS 记录值, 不解释. 转换 (模式产地合成、地名、坐标) 在 12 以后的步骤.
输入: names.tsv (种级名称, 含非有效名)
输出 (02_原始数据/worms/):
  taxdetails_fields.tsv  每行 = 一个名称的一个页面区块: aphia_id, field (页面标签, 如 Environment / Original description /
                         Type data / Descriptive notes / Synonymised names / Type taxon of ...), text (区块纯文本)
  taxdetails_items.tsv   每行 = Type data 或 Descriptive notes 里的一项: aphia_id, section, item_kind
                         (sm=标本, dr=分布/模式产地, note=注释), item_id, label (如 Holotype / type locality contained in /
                         Type locality / Etymology / Depth range / Distribution), value, of_name ('(of X)' 原始组合名),
                         from_synonym (Y=页面标注 [from synonym]), qc_source (如 From editor or global species database),
                         detail_url
用法: python3 04_taxdetails.py <Taxon>
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import data_dir, read_tsv, summary, write_tsv
from worms import WEB, client, html_text, pmap

SP = {"Species", "Subspecies", "Variety", "Forma"}
KIND_URL = {"sm": "specdetails", "dr": "distribution", "note": "notes"}
SKIP_FIELDS = {"Taxonomic edit history", "Licensing"}


def sections(page):
    """按 <label for=...> 切分页面 -> [(标签, 区块HTML)]; 从 AphiaID 标签开始, 避开页头."""
    labs = list(re.finditer(r'<label[^>]*for="([^"]+)"[^>]*>(.*?)</label>', page, re.S))
    out = []
    for i, m in enumerate(labs):
        end = labs[i + 1].start() if i + 1 < len(labs) else page.find("</body>")
        out.append((html_text(m.group(2)), page[m.end():end]))
    k = next((i for i, (lab, _) in enumerate(out) if lab == "AphiaID"), 0)
    return out[k:]


def items(section, body):
    rows = []
    for m in re.finditer(r'<span id="aphia_ct_([a-z]+)_(\d+)"[^>]*>(.*?)</span>', body, re.S):
        kind, iid, inner = m.group(1), m.group(2), m.group(3)
        qc = re.findall(r'aphia_notes_qc_title[^>]*>(.*?)</div>', body[:m.start()], re.S)
        b = re.search(r"<b>(.*?)</b>", inner, re.S)
        text = html_text(inner)
        label = html_text(b.group(1)) if b else ""
        value = text[len(label):].strip() if label and text.startswith(label) else text
        of = re.search(r"\(of (.+?)\)", value)
        if kind == "sm" and not label:                       # 标本: 'Holotype (of X) ZMUC POL 29, geounit ...'
            label = value.split(" ")[0]
        rows.append({"section": section, "item_kind": kind, "item_id": iid, "label": label,
                     "value": re.sub(r"\s*\[from synonym\]\s*taxon\]?", "", value).strip(),
                     "of_name": of.group(1).strip() if of else "",
                     "from_synonym": "Y" if "[from synonym]" in text else "",
                     "qc_source": html_text(qc[-1]) if qc else "",
                     "detail_url": f"{WEB}?p={KIND_URL.get(kind, kind)}&id={iid}"})
    return rows


def one(aid):
    page = client().taxdetails_html(int(aid)) or ""
    f, it = [], []
    for lab, body in sections(page):
        if lab in SKIP_FIELDS or not lab:
            continue
        f.append({"aphia_id": aid, "field": lab, "text": html_text(re.sub(r"<script.*?</script>", "", body, flags=re.S))})
        if lab in ("Type data", "Descriptive notes"):
            it += [{"aphia_id": aid, **r} for r in items(lab, body)]
    return f, it


def main(taxon):
    out = data_dir(taxon, "worms")
    n = read_tsv(out / "names.tsv")
    ids = list(n[n["rank"].isin(SP)].aphia_id)
    res = pmap(one, ids)
    fails = [a for a, r in zip(ids, res) if r is None]
    F = pd.DataFrame([x for r in res if r for x in r[0]])
    I = pd.DataFrame([x for r in res if r for x in r[1]],
                     columns=["aphia_id", "section", "item_kind", "item_id", "label", "value", "of_name", "from_synonym", "qc_source", "detail_url"])
    write_tsv(F, out / "taxdetails_fields.tsv")
    write_tsv(I, out / "taxdetails_items.tsv")
    summary("04_taxdetails", [f"{len(ids)} pages: {len(F)} field blocks; {len(I)} type-data/notes items on {I.aphia_id.nunique()} names; failed {len(fails)}",
                              "items: " + "; ".join(f"{k} {v}" for k, v in (I.item_kind + ":" + I.label.str.lower()).value_counts().head(8).items()),
                              f"-> {out / 'taxdetails_fields.tsv'} , taxdetails_items.tsv"])


if __name__ == "__main__":
    main(sys.argv[1])
