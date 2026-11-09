"""07 属性与俗名 (提取层): WoRMS attributes (体长、功能群、AMBI 等, 树状结构展开) + vernaculars -> 两个 TSV

只照搬 WoRMS 记录值.
输入: names.tsv (种级名称)
输出 (02_原始数据/worms/):
  attributes.tsv   每行 = 一个属性值: aphia_id, measurement_type, measurement_value, qualifiers (子属性 'Unit=mm; Type=maximum; ...'),
                   source_id, reference, qualitystatus, aphia_id_inherited (属性继承自哪个上级类群)
  vernaculars.tsv  每行 = 一个俗名: aphia_id, vernacular, language_code, language
用法: python3 07_attributes.py <Taxon>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import clean, data_dir, read_tsv, summary, write_tsv
from worms import client, pmap

SP = {"Species", "Subspecies", "Variety", "Forma"}


def flatten(aid, nodes, quals=()):
    rows = []
    for x in nodes or []:
        q = quals + ((clean(x.get("measurementType")), clean(x.get("measurementValue"))),)
        kids = x.get("children") or []
        if not quals:  # 顶层 = 一个属性, 其下子节点作为限定词
            sub = []

            def walk(ns):
                for k in ns or []:
                    sub.append(f"{clean(k.get('measurementType'))}={clean(k.get('measurementValue'))}")
                    walk(k.get("children"))
            walk(kids)
            rows.append({"aphia_id": aid, "measurement_type": q[0][0], "measurement_value": q[0][1],
                         "qualifiers": "; ".join(sub), "source_id": clean(x.get("source_id")),
                         "reference": clean(x.get("reference")), "qualitystatus": clean(x.get("qualitystatus")),
                         "aphia_id_inherited": clean(x.get("AphiaID_Inherited"))})
    return rows


def one(aid):
    c = client()
    att = flatten(aid, c.attributes(int(aid)))
    ver = [{"aphia_id": aid, "vernacular": clean(v.get("vernacular")), "language_code": clean(v.get("language_code")),
            "language": clean(v.get("language"))} for v in (c.vernaculars(int(aid)) or [])]
    return att, ver


def main(taxon):
    out = data_dir(taxon, "worms")
    n = read_tsv(out / "names.tsv")
    ids = list(n[(n["rank"].isin(SP)) | (n["rank"] == "Genus")].aphia_id)
    res = pmap(one, ids)
    A = pd.DataFrame([x for r in res if r for x in r[0]],
                     columns=["aphia_id", "measurement_type", "measurement_value", "qualifiers", "source_id", "reference", "qualitystatus", "aphia_id_inherited"])
    V = pd.DataFrame([x for r in res if r for x in r[1]], columns=["aphia_id", "vernacular", "language_code", "language"])
    write_tsv(A, out / "attributes.tsv")
    write_tsv(V, out / "vernaculars.tsv")
    summary("07_attributes", [f"{len(A)} attribute values on {A.aphia_id.nunique()} names; {len(V)} vernaculars; failed {sum(r is None for r in res)}",
                              "types: " + "; ".join(f"{k} {v}" for k, v in A.measurement_type.value_counts().head(6).items()),
                              f"-> {out / 'attributes.tsv'} , vernaculars.tsv"])


if __name__ == "__main__":
    main(sys.argv[1])
