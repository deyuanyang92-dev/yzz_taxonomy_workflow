"""NCBI 响应的纯解析函数 (无网络, 便于离线测试)."""
import csv
import io


def parse_runinfo(text):
    """SraRunInfo CSV -> [dict]; 去 BOM、空行和重复表头行 (分页拼接/网页导出常见)."""
    text = text.lstrip("﻿")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        run = (r.get("Run") or "").strip()
        if run and run != "Run":
            rows.append({k.lstrip("﻿"): (v or "") for k, v in r.items() if k is not None})
    return rows


def _text(el, path):
    x = el.find(path)
    return (x.text or "").strip() if x is not None and x.text else ""


def parse_sra_packages(xml):
    """efetch db=sra 完整 XML -> 每个 RUN 一行 (仿 kingfisher annotate 字段; 不取联系人姓名/邮箱).

    样本属性 TAG -> 列名 (原样); 无 VALUE 的跳过; 与已有字段重名的加前缀 sample_.
    """
    import json
    from defusedxml import ElementTree as ET
    rows = []
    for pkg in ET.fromstring(xml).iter("EXPERIMENT_PACKAGE"):
        org = pkg.find("Organization")
        links = []
        for x in pkg.findall("STUDY/STUDY_LINKS/STUDY_LINK/XREF_LINK"):
            links.append({"db": _text(x, "DB").lower(), "id": _text(x, "ID")})
        for x in pkg.findall("STUDY/STUDY_LINKS/STUDY_LINK/URL_LINK"):
            links.append({"label": _text(x, "LABEL"), "url": _text(x, "URL")})
        d = {
            "experiment_title": _text(pkg, "EXPERIMENT/TITLE"),
            "design_description": _text(pkg, "EXPERIMENT/DESIGN/DESIGN_DESCRIPTION"),
            "study_title": _text(pkg, "STUDY/DESCRIPTOR/STUDY_TITLE"),
            "study_abstract": _text(pkg, "STUDY/DESCRIPTOR/STUDY_ABSTRACT").replace("\r", ""),
            "study_links": json.dumps(links, ensure_ascii=False) if links else "",
            "organisation": _text(org, "Name") if org is not None else "",
            "organisation_department": _text(org, "Address/Department") if org is not None else "",
            "organisation_country": _text(org, "Address/Country") if org is not None else "",
            "sample_title": _text(pkg, "SAMPLE/TITLE"),
            "sample_alias": (pkg.find("SAMPLE").get("alias", "") if pkg.find("SAMPLE") is not None else ""),
            "number_of_runs_for_sample": str(len(pkg.findall("RUN_SET/RUN"))),
        }
        for a in pkg.findall("SAMPLE/SAMPLE_ATTRIBUTES/SAMPLE_ATTRIBUTE"):
            tag, val = _text(a, "TAG"), a.find("VALUE")
            if not tag or val is None or val.text is None:
                continue
            key = tag if tag not in d and tag != "Run" else "sample_" + tag
            d[key] = val.text.strip()
        for run in pkg.findall("RUN_SET/RUN"):
            rows.append({"Run": run.get("accession", ""), **d})
    return rows


RANKS = ("phylum", "class", "order", "family", "genus", "species")


def norm_taxid(s):
    """'46593.0' / ' 46593 ' -> '46593'; 空值 -> ''."""
    s = str(s or "").strip()
    if s.lower() in ("", "nan", "none"):
        return ""
    return s[:-2] if s.endswith(".0") else s


def parse_taxonomy_xml(xml):
    """efetch db=taxonomy XML -> [{TaxID, rank_derived, phylum…species}]; 已合并的旧 taxid (AkaTaxIds) 也各给一行."""
    from defusedxml import ElementTree as ET
    rows = []
    for t in ET.fromstring(xml).findall("Taxon"):
        r = {"TaxID": t.findtext("TaxId", ""), "rank_derived": t.findtext("Rank", "")}
        r.update({k: "" for k in RANKS})
        for x in t.findall("LineageEx/Taxon") + [t]:
            rank = x.findtext("Rank", "")
            if rank in RANKS:
                r[rank] = x.findtext("ScientificName", "")
        rows.append(r)
        for aka in t.findall("AkaTaxIds/TaxId"):
            rows.append({**r, "TaxID": aka.text})
    return rows
