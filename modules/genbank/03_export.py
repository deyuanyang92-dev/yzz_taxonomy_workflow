"""03 导出: g2t 结果 -> 多基因表 Excel + 每基因 FASTA (只做整理, 不改 GenBank 原值).

同一标本的凭证号写法不一致 (COI_ZMMU_MSU_WS399 / 28S_ZMMU_WS399 / WS399) 由 g2t 的 reconcile 步骤 (3b) 处理:
同物种 + 核心编号相同 + 记录中有证据 (同一论文/同日期/同坐标 = 强; 同采集人/同地点/同第一作者 = 中) 才合并,
有矛盾 (日期/国家/坐标不符) 不合并; 判定逐对写入 Voucher reconciliation 表. 本步骤只读结果, 不再自行合并.

输入: 02_原始数据/genbank/g2t/<tag>/ , gb/<tag>/manifest.json, gb/<tag>/*.gb
输出: 04_处理数据/genbank/<Taxon>_GenBank_<tag>_<date>.xlsx ; 02_原始数据/genbank/fasta/<tag>/<gene>.fasta
矩阵中 voucher_standardized = 统一后的凭证号 (去基因前缀、统一分隔符、取最完整写法), voucher_as_submitted = GenBank 原样.
另写 02_原始数据/genbank/matrix_<tag>.tsv 供 04 校正使用.
工作表: Matrix (标本 × 基因, 单元格 = accession.version) / Species x gene / Records / Voucher reconciliation / Not classified / QC / Query
用法: python3 yzz.py genbank 03 <Taxon> [--tag markers]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from Bio import SeqIO
from common import TODAY, data_dir, report_dir, summary, write_tsv
from excel import YELLOW, write_workbook
from g2t.curate import standardize_vouchers

GENE_ORDER = ["mtgenome", "coi", "cox2", "cox3", "cob", "12s", "16s", "18s", "28s", "18-28s", "its1-its2", "h3", "ef-1"]
META = ["specimen_voucher", "isolate", "geo_loc_name", "country", "lat_lon", "collection_date", "collected_by",
        "identified_by", "Ref1Authors", "Ref1Title", "Ref1Journal"]


def join(xs):
    out = []
    for x in xs:
        for y in str(x).split(";"):
            y = y.strip()
            if y and y.lower() != "nan" and y not in out:
                out.append(y)
    return "; ".join(out)


def export(taxon, tag):
    root = data_dir(taxon, "genbank")
    g = root / "g2t" / tag
    man = json.loads((root / "gb" / tag / "manifest.json").read_text(encoding="utf-8"))
    vdir = g / "updated_species_vouchers"
    rfile = vdir / "reconciled_species_voucher.csv"
    rec = pd.read_csv(rfile if rfile.exists() else vdir / "updated_species_voucher.csv", dtype=str).fillna("")
    for c in ("species_voucher_g2t", "voucher_core", "match_basis", "match_confidence", "match_evidence"):
        if c not in rec:
            rec[c] = rec["species_voucher_new"] if c == "species_voucher_g2t" else ("exact" if c == "match_basis" else "")
    allm = pd.read_csv(g / "gb_metadata" / "final.csv", dtype=str).fillna("")

    def full_acc(a, v):  # g2t "Version" may hold only the version number ("1") or the full "AB123.1"
        v = str(v).strip()
        return v if "." in v else (f"{a}.{v}" if v.isdigit() else a)
    acc_ver = {a: full_acc(a, v) for a, v in zip(allm["ACCESSION"], allm.get("Version", allm["ACCESSION"]))}
    rec["accession"] = rec["ACCESSION"].map(lambda a: acc_ver.get(a, a))
    rec["voucher_raw"] = rec["specimen_voucher"].where(rec["specimen_voucher"] != "", rec["isolate"])
    rec["specimen_key"] = rec["species_voucher_new"]
    rep_file = vdir / "reconcile_report.csv"
    recon = pd.read_csv(rep_file, dtype=str).fillna("") if rep_file.exists() else pd.DataFrame()
    # matrix
    genes = [x for x in GENE_ORDER if x in set(rec["gene_type"])] + sorted(set(rec["gene_type"]) - set(GENE_ORDER) - {""})
    rows = []
    for key, grp in rec.groupby("specimen_key", sort=False):
        std, consistent = standardize_vouchers(grp["specimen_voucher"])
        r = {"specimen_key": key, "organism": join(grp["organism"]),
             "voucher_standardized": std, "voucher_as_submitted": join(grp["specimen_voucher"]),
             "voucher_note": "" if consistent else "voucher forms differ beyond gene prefixes/separators; check",
             "n_genes": grp["gene_type"].nunique(),
             "match_basis": grp["match_basis"].iloc[0], "match_confidence": grp["match_confidence"].iloc[0],
             "isolate": join(grp["isolate"])}
        for gn in genes:
            r[gn] = join(grp.loc[grp["gene_type"] == gn, "accession"])
        r["match_evidence"] = grp["match_evidence"].iloc[0]
        for m in META[2:]:
            if m in grp:
                r[m] = join(grp[m])
        rows.append(r)
    mat = pd.DataFrame(rows).sort_values(["organism", "n_genes", "specimen_key"], ascending=[True, False, True])
    # species x gene: number of specimens with >=1 sequence
    sp = mat.groupby("organism").agg(specimens=("specimen_key", "count"),
                                     **{gn: (gn, lambda s: int((s != "").sum())) for gn in genes}).reset_index()
    sp["records"] = sp["organism"].map(rec.groupby("organism").size())
    # records sheet
    rcols = ["gene_type", "accession", "organism", "Length", "Definition", "specimen_key", "match_basis", "match_confidence",
             "voucher_raw", "voucher_core", "species_voucher_g2t", "Assignment_reason", "Conflict", "Conflict_reason", "Date", "TaxonID"] + [m for m in META if m in rec]
    records = rec[[c for c in rcols if c in rec]].sort_values(["organism", "gene_type", "accession"])
    # not classified: g2t record_status.csv lists every input record (assigned / unmatched / filtered + reason)
    stf = g / "labeled_genes" / "record_status.csv"
    if stf.exists():
        st = pd.read_csv(stf, dtype=str).fillna("")
        nc = st[st["status"] != "assigned"].copy()
        nc["accession"] = nc["ACCESSION"].map(lambda a: acc_ver.get(a, a))
        nc = nc[["accession", "Organism", "Length", "Definition", "status", "reason"]]
    else:  # g2t without record_status (older version)
        nc = allm[~allm["ACCESSION"].isin(rec["ACCESSION"])].copy()
        nc["accession"] = nc["ACCESSION"].map(lambda a: acc_ver.get(a, a))
        nc["status"], nc["reason"] = "", "not assigned (reason unknown: g2t without record_status.csv)"
        nc = nc[["accession", "Organism", "Length", "Definition", "status", "reason"]]
    # QC
    qc = []
    if len(recon):
        for _, x in recon[~recon["decision"].str.startswith("merged")].iterrows():
            qc.append({"issue": "voucher variants not merged — " + x["decision"].replace("not merged: ", ""),
                       "core_id": x["voucher_core"],
                       "detail": f"{x['group_a']} [{x['genes_a']}] vs {x['group_b']} [{x['genes_b']}]"
                                 + (f"; {x['evidence']}" if x["evidence"] else "")})
    for key, grp in rec.groupby(["specimen_key", "gene_type"]):
        if len(grp) > 1:
            qc.append({"issue": "several accessions for one specimen and gene", "core_id": key[0],
                       "detail": f"{key[1]}: {', '.join(grp['accession'])}"})
    if (rec["Conflict"].astype(str).str.lower() == "true").any():
        for _, x in rec[rec["Conflict"].astype(str).str.lower() == "true"].iterrows():
            qc.append({"issue": "g2t gene-type conflict", "core_id": x["accession"], "detail": x.get("Conflict_reason", "")})
    qc = pd.DataFrame(qc, columns=["issue", "core_id", "detail"])
    query = pd.DataFrame([(k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in man.items()],
                         columns=["field", "value"])
    # FASTA per gene
    fa = root / "fasta" / tag
    fa.mkdir(parents=True, exist_ok=True)
    seqs = {}
    for f in sorted((root / "gb" / tag).glob("*.gb")):
        for s in SeqIO.parse(str(f), "genbank"):
            seqs[s.id.split(".")[0]] = s
    nfa = {}
    for gn in genes:
        lines = []
        for _, x in rec[rec["gene_type"] == gn].iterrows():
            s = seqs.get(x["ACCESSION"])
            if s is None:
                continue
            hdr = f"{x['accession']}|{x['organism'].replace(' ', '_')}|{x['specimen_key']}"
            lines.append(f">{hdr}\n{str(s.seq)}")
        (fa / f"{gn}.fasta").write_text("\n".join(lines) + "\n", encoding="utf-8")
        nfa[gn] = len(lines)
    out = report_dir(taxon, "genbank") / f"{taxon}_GenBank_{tag}_{TODAY}.xlsx"
    write_tsv(mat, root / f"matrix_{tag}.tsv")          # input of step 04 (curation)
    out = write_workbook(out, {"Matrix": mat, "Species x gene": sp, "Records": records,
                               "Voucher reconciliation": recon, "Not classified": nc, "QC": qc, "Query": query},
                         freeze={"Matrix": "C2", "Records": "C2"},
                         shade={"Matrix": [("match_confidence", "medium", YELLOW)]})
    multi = int((mat["n_genes"] >= 2).sum())
    return [f"{tag}: {len(allm)} 条 -> 已归类 {len(rec)} ({len(genes)} 个基因), 未匹配 {int((nc['status'] == 'unmatched').sum())}, "
            f"被过滤 {int((nc['status'] == 'filtered').sum())} (原因见 Not classified 表); "
            f"标本 {len(mat)} (≥2 基因 {multi}; 凭证号核对合并 {int((mat['match_basis'] == 'reconciled').sum())}, "
            f"其中中等置信 {int((mat['match_confidence'] == 'medium').sum())}); 物种 {len(sp)}; QC {len(qc)}",
            "FASTA: " + ", ".join(f"{k} {v}" for k, v in nfa.items()),
            f"Excel: {out}"]


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("taxon")
    p.add_argument("--tag", default="")
    a, _ = p.parse_known_args(argv)
    root = data_dir(a.taxon, "genbank") / "g2t"
    tags = [a.tag] if a.tag else sorted(d.name for d in root.iterdir() if d.is_dir())
    lines = []
    for t in tags:
        lines += export(a.taxon, t)
    summary("03_export", lines)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
