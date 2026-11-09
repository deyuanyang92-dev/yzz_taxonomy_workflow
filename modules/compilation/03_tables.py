"""03 结构化层: 子代理核对结果 -> 08_知识库/结构化/{work,treatment,name_usage}.csv (Travisia 同结构, 供 85 汇编脚本).
输入: 结构化/treatment_candidates.tsv (02 步), 结构化/confirm/out_*.tsv (子代理), 01_文献 总表 (文献清单).
证据级别 (Travisia 性状定义与计数规则.md):
  有形态内容 (description / short_description): WoRMS 原始描述 -> L3; 文中检视模式标本或 WoRMS 注明模式 -> L2; 其余 -> L4
  record_only / key_or_table / mention -> L5 (只列出); not_found / wrong_file -> 不入表, 写 结构化/03_待核.tsv
original_text = KB 中起止页 OCR/文字层, 按标题行自动截取 (须对照页图; 不是人工校对文本). 译文暂空.
用法: python3 yzz.py compilation 03 <项目目录>
"""
import glob
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import importlib.util

import pandas as pd
import regex

_sp = importlib.util.spec_from_file_location("acc", Path(__file__).with_name("account_text.py"))
ACC = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(ACC)      # 记述原文: 去页眉页脚/表格/图注, [p. N] 页码标记 (脚本 89)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfg  # noqa: E402  项目根目录与配置
ROOT, S, DB, TAB, PDFDIR = cfg.ROOT, cfg.S, cfg.KB, cfg.TAB, cfg.PDFDIR
HEAD = re.compile(r"^[A-Z][a-z]+\s+(\([A-Z][a-z]+\)\s+)?[a-z]{3,}(\s+[a-z]{3,})?\s*,?\s*(\(?[A-Z][A-Za-zé\-ü&. ]+,?\s*\d{4}\)?|n\.\s*sp|sp\.\s*n|new species|nov)")
STOP = {"en": " the and of with is are ", "de": " der die und mit ist sind ", "fr": " le les et des avec sont ",
        "es": " el los y con son del ", "la": " et cum in ad sunt est "}


def taxon_name(valid):
    """'Eunice antipathum (Pourtalès, 1867)' -> 'Eunice antipathum'."""
    w = str(valid).split()
    out = [w[0]] + [x for x in w[1:3] if x.islower() and x.isalpha()]
    return " ".join(out[:3])


def surname(authors):
    a = str(authors).split(";")[0].split(",")[0].strip()
    a = unicodedata.normalize("NFKD", a).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z\-]", "", a.replace("Treadwellaron", "Treadwell")) or "Anon"


def lang(t):
    t = " " + re.sub(r"\s+", " ", t.lower()) + " "
    sc = {k: sum(t.count(f" {w} ") for w in v.split()) for k, v in STOP.items()}
    return max(sc, key=sc.get) if max(sc.values()) else ""


def cut(pages, ep, single):
    """连续页文字 -> 该种记述 (起: 首个含种加词的标题行/首次出现; 止: 其后第一个他种标题行)."""
    pe = regex.compile(rf"(?:{re.escape(ep.lower())}){{e<=1}}" if len(ep) >= 6 else rf"\b{re.escape(ep.lower())}\b")
    lines = []
    for p, t in pages:
        lines.append(f"[PDF p{p}]")
        lines += [x for x in (t or "").splitlines() if x.strip()]
    hit = [i for i, x in enumerate(lines) if pe.search(x.lower())]
    if not hit:
        return "\n".join(lines), "种加词未在文字中找到, 保留整页"
    head = [i for i in hit if HEAD.match(lines[i].strip())]
    a = head[0] if head else hit[0]
    b = len(lines)
    for i in range(a + 1, len(lines)):
        if HEAD.match(lines[i].strip()) and not pe.search(lines[i].lower()):
            b = i
            break
    note = "自动截取: 起于" + ("标题行" if head else "首次出现") + ("; 止于下一他种标题" if b < len(lines) else "; 至末页尾")
    if len("\n".join(lines[a:b])) < 400:
        return "\n".join(lines), "截取过短 (<400 字), 保留整页"
    return "\n".join(lines[a:b]), note


def main():
    cand = pd.read_csv(S / "treatment_candidates.tsv", sep="\t", dtype=str).fillna("")
    outs = [pd.read_csv(f, sep="\t", dtype=str, on_bad_lines="warn").fillna("") for f in sorted(glob.glob(str(S / "confirm" / "out_*.tsv")))]
    conf = pd.concat(outs).drop_duplicates("row", keep="last")
    fx = S / "confirm" / "fix_out.tsv"          # 二次核对: 记述在同一文献的另一份 PDF (分册/副本) -> 覆盖该行
    if fx.exists():
        f = pd.read_csv(fx, sep="\t", dtype=str).fillna("").rename(columns={"file": "file_fix"}).drop_duplicates("row", keep="last")
        conf = pd.concat([conf[~conf.row.isin(f.row)], f])
    m = cand.merge(conf, on="row", how="inner", suffixes=("_cand", ""))
    if "file_fix" in m:
        m["file"] = m.file_fix.where(m.file_fix.fillna("") != "", m.file)
    m = m.fillna("")
    sup = S / "supplement_accounts.tsv"          # WoRMS 未挂的文献 (如 Monro 1934 P. sinensis 原始描述), 用户提供
    SUPCIT = {}
    if sup.exists():
        x = pd.read_csv(sup, sep="\t", dtype=str).fillna("")
        SUPCIT = dict(zip(x.sid, x.citation))
        x = x.rename(columns={"sid": "row", "taxon_valid_full": "valid_taxon"}).assign(
            ref_no=lambda d: d.row, worms_page="", note="", offset="", confidence="high", source_id="", aphia_id="")
        m = pd.concat([m, x[[c for c in x.columns if c in m.columns or c in ("row",)]]], ignore_index=True).fillna("")
    lit = pd.read_excel(TAB, "文献清单", dtype=str).fillna("")
    con = sqlite3.connect(DB)
    try:                                         # 已知属名 (标题行判定)
        ACC.GENERA.update(n.split()[0] for (n,) in con.execute("select name from worms_names union select valid_name from worms_names") if n)
    except sqlite3.Error:
        pass
    ACC.GENERA.update({taxon_name(v).split()[0] for v in m.valid_taxon} | {str(n).split()[0] for n in m.scientific_name if str(n).strip()})
    HEADS = {}

    # work
    ok = m[~m.content.isin(["not_found", "wrong_file", "not_in_kb"])]
    refs = ok[["ref_no", "authors", "year", "file"]].drop_duplicates(["ref_no", "file"]).sort_values(["year", "ref_no"])
    used, wid = {}, {}
    for ref in refs.ref_no.unique():
        r = refs[refs.ref_no == ref].iloc[0]
        base = f"{surname(r.authors)}{r.year}"
        k = used.get(base, 0)
        used[base] = k + 1
        wid[ref] = base + ("abcdefghij"[k] if k else "")
    for b, n in used.items():          # 同名同年 -> 首篇也加 a
        if n > 1:
            for ref, w in wid.items():
                if w == b:
                    wid[ref] = b + "a"
    fid = {}                            # (ref, file) -> work_id; 同一文献分在几个 PDF 时加 -pdf2
    for ref in refs.ref_no.unique():
        for k, fn in enumerate(refs[refs.ref_no == ref].file):
            fid[(ref, fn)] = wid[ref] + (f"-pdf{k + 1}" if k else "")
    L = lit.set_index("ref_no") if "ref_no" in lit.columns else pd.DataFrame()
    W = []
    for r in refs.itertuples():
        x = L.loc[r.ref_no] if r.ref_no in L.index else {}
        x = x.iloc[0] if isinstance(x, pd.DataFrame) else x
        g = (lambda k: str(x.get(k, "")) if len(x) else "")
        cit = SUPCIT.get(r.ref_no) or f"{r.authors} ({r.year}). {re.sub(r'<[^>]+>', '', g('title'))}. {g('journal_or_publisher')} {g('volume_issue_pages')}".strip()
        doi = g("doi") or (re.search(r"10\.\d{4,}/\S+", cit).group() if re.search(r"10\.\d{4,}/\S+", cit) else "")
        W.append({"work_id": fid[(r.ref_no, r.file)], "author_short": surname(r.authors) + (" et al." if r.authors.count(";") >= 2 else ""),
                  "citation": cit, "year_nominal": r.year, "ref_no": r.ref_no, "local_path": str(PDFDIR / r.file),
                  "doi": doi, "held": "yes", "note": "补充 (WoRMS 未挂)" if r.ref_no in SUPCIT else ""})
    pd.DataFrame(W).to_csv(S / "work.csv", index=False, encoding="utf-8-sig")

    # treatment + name_usage
    T, NU, bad = [], [], []
    for r in m.itertuples():
        c = r.content.strip()
        if c in ("not_found", "wrong_file", "not_in_kb") or not r.pdf_start.strip().isdigit():
            bad.append({**r._asdict()})
            continue
        tax = taxon_name(r.valid_taxon)
        a, b = int(r.pdf_start), int(r.pdf_end) if r.pdf_end.strip().isdigit() else int(r.pdf_start)
        kb = {p: (t, src) for p, t, src in con.execute("select page_no, text, source from pages where file=? and page_no between ? and ?", (r.file, a, b))}
        desc = c in ("description", "short_description")
        if not desc:
            lev = "L5"
        elif r.level.startswith("L3"):
            lev = "L3"
        elif r.type_material.strip() or r.level.startswith("L2"):
            lev = "L2"
        else:
            lev = "L4"
        if r.printed_start.strip().isdigit():
            off = int(r.printed_start) - a
        else:
            off = int(float(r.offset)) if str(r.offset).strip() not in ("", "nan") else None
        if r.file not in HEADS:
            HEADS[r.file] = ACC.running_heads([t for (t,) in con.execute("select text from pages where file=?", (r.file,))])
        text, note = ACC.account(str(PDFDIR / r.file), a, b, r.scientific_name.split()[-1], off, kb, HEADS[r.file]) if desc else ("", "")
        pr = f"{r.printed_start}-{r.printed_end}" if r.printed_end and r.printed_end != r.printed_start else r.printed_start
        pages = f"{pr or r.worms_page} (PDF {a}-{b})" if b > a else f"{pr or r.worms_page} (PDF {a})"
        w = fid[(r.ref_no, r.file)]
        T.append({"treatment_id": f"{tax.split()[-1]}:{w}:{r.row}", "taxon": tax, "taxon_valid_full": r.valid_taxon, "work_id": w,
                  "pages": pages, "kind": f"{c}; WoRMS: {r.use}" + (f" ({r.note})" if r.note else ""), "level": lev,
                  "material": r.type_material, "compared_context": "", "language": lang(text) if text else "",
                  "original_text": text, "text_note": ("OCR / text-layer text, not proofread; " + note) if text else "",
                  "translation_en": "", "figures": r.fig_pages, "name_as_printed": r.name_as_printed or r.scientific_name,
                  "confidence": r.confidence, "comment": r.comment, "row": r.row, "scientific_name": r.scientific_name})
        NU.append({"usage_id": f"{tax.split()[-1]}:{r.row}", "taxon": tax, "name_as_printed": r.name_as_printed or r.scientific_name,
                   "work_id": w, "pages": pages, "figures": r.fig_pages, "usage_type": f"{r.use}; {c}",
                   "taxon_concept_note": r.comment})
    pd.DataFrame(T).to_csv(S / "treatment.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(NU).to_csv(S / "name_usage.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(bad).to_csv(S / "03_待核.tsv", sep="\t", index=False)
    t = pd.DataFrame(T)
    # 每个有效分类单元必须有原始描述 (用户 2026-11-08): 该种加词 (前 5 字母, 容词尾变化) 的 L3 记述
    allv = pd.read_excel(TAB, "物种×文献", dtype=str).fillna("").valid_taxon.unique()
    miss = []
    for v in allv:
        tax = taxon_name(v)
        e = tax.split()[-1][:5].lower()
        sub = t[(t.taxon == tax) & (t.level == "L3")] if len(t) else t
        if not any(n.split()[-1][:5].lower() == e for n in sub.get("scientific_name", [])):
            miss.append({"valid_taxon": v, "taxon": tax, "L3_of_other_names": "; ".join(sub.get("scientific_name", [])),
                         "n_accounts": int((t.taxon == tax).sum()) if len(t) else 0})
    pd.DataFrame(miss).to_csv(S / "03_缺原始描述.tsv", sep="\t", index=False)
    print(f"[03] 缺原始描述 {len(miss)}/{len(allv)} 分类单元 -> {S / '03_缺原始描述.tsv'} (明细见总表工作表 '缺原始描述')")
    for x in miss:                                   # 逐个列出, 不只给数字 (用户 2026-11-08: 没有原始描述要告诉我)
        print(f"     缺原始描述: {x['valid_taxon']}")
    print(f"[03] work {len(W)}, treatment {len(T)} (levels {t.level.value_counts().to_dict() if len(t) else {}}), "
          f"taxa {t.taxon.nunique() if len(t) else 0}, 待核 {len(bad)}; 未核对 {len(cand) - len(m)} 行")


if __name__ == "__main__":
    main()
    import subprocess
    subprocess.run([sys.executable, str(Path(__file__).with_name("supplement_table.py")), str(cfg.ROOT)])   # 补充文献写回总表
