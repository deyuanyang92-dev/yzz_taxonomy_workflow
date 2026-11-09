"""01 count: GenBank records + SRA samples -> taxon x data-type count matrix (TSV) for 02_plot.py / molheat.R.

Default names = NCBI organism names as submitted. --names worms (optional) maps them to WoRMS valid names.

Inputs (any of them; default = this taxon's yzz outputs):
  --genbank  yzz genbank Excel (sheet Records) or any table with an organism column + gene column (g2t gene_type)
  --sra      organise-sra / yzz sra samples.tsv (ScientificName, category_derived, family, BioSample, n_runs, total_Gb)
Rows:
  --level genus    one row per genus; family-level / unidentified names -> "<Family> und."
  --level species  one row per name; --genus Marphysa keeps that genus only (zoom panel)
  --pool-informal  sp   (default) "Marphysa sp. E HA-2019", "Marphysa sp." -> "Marphysa sp."; cf./aff. names kept
                   all  cf./aff. names pooled too;  none  every NCBI name its own row
  --genome   auto (default: NCBI Assembly, "<family>[Organism:exp] AND latest[filter]", one count per assembly)
             | assemblies.tsv (column organism) | none
Columns (default = Nereididae figure, Ye et al. 2024): coi cox2 cox3 cob 12s 16s 18s 28s its h3 mt lcWGS RNA Genome
  GenBank genes renamed with --rename (default its1-its2=its, mtgenome=mt); a mitogenome also counts in --mt-expand genes.
  SRA columns: --sra-columns "lcWGS=shallow_WGS;RNA=RNA-Seq": lcWGS = low-coverage short-read WGS (organise-sra shallow_WGS, 0.5-10 Gb/sample);
  deep WGS, long-read and Hi-C of genome projects are not counted (their assemblies are in Genome).
  Unit: GenBank = records; SRA = --sra-unit samples (BioSample, default) | runs | Gb.
Outputs: <out>.tsv (matrix; first column taxon) + <out>_names.tsv (every input name -> row, source, count).

  python3 yzz.py molheat 01 Eunicidae --level genus --out Eunicidae_genus
  python3 yzz.py molheat 01 Eunicidae --level species --genus Marphysa --out Marphysa_species
  python3 modules/molheat/01_count.py Eunicidae --genbank Records.xlsx --sra samples.tsv --family Eunicidae ...
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
sys.path.insert(0, str(HERE))
from taxname import is_higher_taxon  # noqa: E402

DEF_COLS = "coi,cox2,cox3,cob,12s,16s,18s,28s,its,h3,mt,lcWGS,RNA,Genome"
DEF_RENAME = "its1-its2=its,mtgenome=mt,mitogenome=mt,cytb=cob,cox1=coi"
DEF_MT = "coi,cox2,cox3,cob,12s,16s"
DEF_SRA = "lcWGS=shallow_WGS;RNA=RNA-Seq"
SP_TOKENS = {"sp.", "spp.", "sp", "spp"}
QUAL = {"cf.", "aff.", "cf", "aff", "nr."}
NON_TAXON = {"marine", "uncultured", "unidentified", "unclassified", "environmental", "metagenome"}


def kv(s, sep=",", eq="="):
    return dict(x.split(eq, 1) for x in s.split(sep) if eq in x) if s else {}


def read_any(path, sheet=None):
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        xl = pd.ExcelFile(p)
        sh = sheet or ("Records" if "Records" in xl.sheet_names else xl.sheet_names[0])
        return pd.read_excel(p, sheet_name=sh, dtype=str).fillna("")
    return pd.read_csv(p, sep="\t" if p.suffix.lower() in (".tsv", ".txt") else ",", dtype=str).fillna("")


def pick_col(df, wanted, given=None):
    if given:
        return given
    for w in wanted:
        if w in df.columns:
            return w
    raise SystemExit(f"column not found (tried {wanted}); columns: {list(df.columns)[:20]}")


def genus_key(name, family):
    toks = name.split()
    if not toks or toks[0].lower() in NON_TAXON or is_higher_taxon(toks[0]):
        fam = toks[0] if toks and is_higher_taxon(toks[0]) else family
        return f"{fam} und."
    return toks[0]


def species_key(name, family, pool):
    toks = name.split()
    if not toks or toks[0].lower() in NON_TAXON or is_higher_taxon(toks[0]):
        return genus_key(name, family)
    g = toks[0]
    if len(toks) == 1:
        return f"{g} sp."
    second = toks[1].lower()
    if second in SP_TOKENS:
        return f"{g} sp." if pool in ("sp", "all") else name
    if second in QUAL:
        if pool == "all":
            return f"{g} sp."
        nxt = toks[2].lower() if len(toks) > 2 else "sp."
        if nxt in SP_TOKENS:                                 # "Marphysa cf. sp. E" -> sp.
            return f"{g} sp." if pool in ("sp", "all") else name
        return f"{g} {toks[1]} {toks[2]}" if pool == "sp" else name   # drop informal tail: "M. cf. hentscheli JZ-2010"
    if not re.fullmatch(r"[a-z][a-z-]+", toks[1]):          # unusual second word -> informal
        return f"{g} sp." if pool in ("sp", "all") else name
    return f"{g} {toks[1]}" if pool != "none" else name


def ncbi_assemblies(term):
    """NCBI Assembly (latest versions only) -> DataFrame accession, organism, level, refseq_category, taxid, submitted."""
    import json
    import time
    import urllib.parse
    import urllib.request
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    key = {}
    cfg = HERE.parents[1] / "config" / "ncbi.json"
    if cfg.exists():
        c = json.loads(cfg.read_text(encoding="utf-8"))
        key = {k: v for k, v in (("api_key", c.get("api_key")), ("email", c.get("email"))) if v}

    def get(ep, **kw):
        q = urllib.parse.urlencode({**kw, **key, "retmode": "json", "tool": "yzz-molheat"})
        for k in range(3):
            try:
                with urllib.request.urlopen(base + ep + "?" + q, timeout=60) as r:
                    return json.load(r)
            except Exception:
                if k == 2:
                    raise
                time.sleep(3 * (k + 1))
    ids = get("esearch.fcgi", db="assembly", term=term, retmax=10000)["esearchresult"]["idlist"]
    rows = []
    for i in range(0, len(ids), 200):
        res = get("esummary.fcgi", db="assembly", id=",".join(ids[i:i + 200]))["result"]
        for u in ids[i:i + 200]:
            r = res[u]
            rows.append({"accession": r.get("assemblyaccession", ""),
                         "organism": re.sub(r"\s*\(.*\)$", "", r.get("organism", "")).strip(),
                         "level": r.get("assemblystatus", ""), "refseq_category": r.get("refseq_category", ""),
                         "taxid": r.get("speciestaxid", ""), "assembly_name": r.get("assemblyname", ""),
                         "submitted": r.get("submissiondate", "")[:10], "submitter": r.get("submitterorganization", "")})
    return pd.DataFrame(rows, columns=["accession", "organism", "level", "refseq_category", "taxid", "assembly_name",
                                       "submitted", "submitter"])


def worms_map(names, family):
    from worms_match import match_names
    res = match_names(names, family=family)
    out = {}
    for n in names:
        r = res.get(n) or {}
        q = r.get("qualifier", "")
        out[n] = (r.get("valid_name") or n) if (r.get("valid_name") and not q) else n
    return out, res


def main(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("taxon", help="label + default input lookup in projects/<taxon>/")
    p.add_argument("--genbank", action="append", default=[], help="repeatable; '' to skip GenBank")
    p.add_argument("--genbank-sheet")
    p.add_argument("--organism-col")
    p.add_argument("--gene-col")
    p.add_argument("--sra", help="samples.tsv; 'none' to skip SRA")
    p.add_argument("--genome", default="auto", help="auto (NCBI Assembly) | assemblies.tsv | none")
    p.add_argument("--genome-term", help='Entrez term for --genome auto (default "<family>[Organism:exp] AND latest[filter]")')
    p.add_argument("--family", help="family for 'und.' rows and SRA filter (default = taxon)")
    p.add_argument("--level", choices=["genus", "species"], default="genus")
    p.add_argument("--genus", help="species level: keep this genus only (comma list allowed)")
    p.add_argument("--pool-informal", choices=["sp", "all", "none"], default="sp")
    p.add_argument("--names", choices=["ncbi", "worms"], default="ncbi")
    p.add_argument("--columns", default=DEF_COLS, help="output columns in order; 'auto' = every gene found")
    p.add_argument("--rename", default=DEF_RENAME, help="gene renames old=new,...")
    p.add_argument("--mt-expand", default=DEF_MT, help="genes a mitogenome also counts in; 'none' to switch off")
    p.add_argument("--sra-columns", default=DEF_SRA)
    p.add_argument("--sra-unit", choices=["samples", "runs", "Gb"], default="samples")
    p.add_argument("--out", help="output prefix (default projects/<taxon>/04_处理数据/molheat/<taxon>_<level>)")
    a = p.parse_args(argv)
    fam = a.family or a.taxon
    rename = kv(a.rename)
    mt_genes = [] if a.mt_expand == "none" else a.mt_expand.split(",")
    rows = []                                                   # (name, column, count, source)

    gb_files = [g for g in a.genbank if g]
    if not a.genbank:
        from common import report_dir
        from common import data_dir
        found = sorted((data_dir(a.taxon, "genbank") / "gb2taxonomy" / "03_results").glob(f"{a.taxon}_GenBank_markers_*.xlsx"))
        gb_files = found[-1:]
    for f in gb_files:
        df = read_any(f, a.genbank_sheet)
        oc = pick_col(df, ["organism", "Organism", "ScientificName", "species"], a.organism_col)
        gc = pick_col(df, ["gene_type", "gene", "Gene", "marker"], a.gene_col)
        for o, g in zip(df[oc], df[gc]):
            g = rename.get(g.lower(), g.lower()) if g.lower() not in ("wgs", "rna") else g
            rows.append((o.strip(), g, 1, "GenBank"))
            if g == "mt":
                rows += [(o.strip(), x, 1, "GenBank (mitogenome)") for x in mt_genes]

    sra_file = a.sra
    if sra_file is None:
        from common import data_dir
        cand = data_dir(a.taxon, "sra") / "samples.tsv"
        sra_file = str(cand) if cand.exists() else "none"
    if sra_file != "none":
        s = read_any(sra_file)
        if "family" in s.columns and fam:
            s = s[s["family"] == fam]
        cat2col = {c: col for col, cats in kv(a.sra_columns, ";").items() for c in cats.split("+")}
        for _, x in s.iterrows():
            col = cat2col.get(x["category_derived"])
            if not col:
                continue
            n = 1 if a.sra_unit == "samples" else (int(x.get("n_runs") or 1) if a.sra_unit == "runs"
                                                   else round(float(x.get("total_Gb") or 0), 1))
            rows.append((x["ScientificName"].strip(), col, n, f"SRA ({x['category_derived']})"))

    asm = None
    if a.genome == "auto":
        term = a.genome_term or f"{fam}[Organism:exp] AND latest[filter]"
        asm = ncbi_assemblies(term)
        print(f"  NCBI Assembly: {term} -> {len(asm)} assemblies")
    elif a.genome != "none":
        asm = read_any(a.genome)
    if asm is not None:
        rows += [(o.strip(), "Genome", 1, f"NCBI Assembly ({lv})") for o, lv in
                 zip(asm["organism"], asm["level"] if "level" in asm else [""] * len(asm))]

    t = pd.DataFrame(rows, columns=["name", "column", "count", "source"])
    if t.empty:
        raise SystemExit("no input records")
    t["name_used"] = t["name"]
    if a.names == "worms":
        mp, _ = worms_map(sorted(set(t["name"])), fam)
        t["name_used"] = t["name"].map(mp)
    key = (lambda n: genus_key(n, fam)) if a.level == "genus" else (lambda n: species_key(n, fam, a.pool_informal))
    t["row"] = t["name_used"].map(key)
    if a.level == "species" and a.genus:
        keep = set(a.genus.split(","))
        t = t[t["row"].str.split().str[0].isin(keep)]
    cols = sorted(set(t["column"])) if a.columns == "auto" else a.columns.split(",")
    dropped = sorted(set(t["column"]) - set(cols))
    m = t[t["column"].isin(cols)].pivot_table(index="row", columns="column", values="count", aggfunc="sum", fill_value=0)
    m = m.reindex(columns=cols, fill_value=0)
    und = [r for r in m.index if r.endswith(" und.")]
    sp = [r for r in m.index if r.endswith(" sp.") and r not in und]
    rest = sorted(r for r in m.index if r not in und and r not in sp)
    if a.level == "species":                                   # sp. after the named species of its genus
        order = und + sorted(rest + sp, key=lambda r: (r.split()[0], r.endswith(" sp."), r))
    else:
        order = und + rest + sp
    m = m.loc[order]
    m.index.name = "taxon"

    if a.out:
        out = Path(a.out)
    else:
        from common import report_dir
        out = report_dir(a.taxon, "molheat") / f"{a.taxon}_{a.level}" if a.level == "genus" else \
            report_dir(a.taxon, "molheat") / f"{(a.genus or a.taxon).replace(',', '_')}_species"
    out.parent.mkdir(parents=True, exist_ok=True)
    m.to_csv(f"{out}.tsv", sep="\t")
    nm = t.groupby(["name", "name_used", "row", "source"])["count"].sum().reset_index()
    nm.to_csv(f"{out}_names.tsv", sep="\t", index=False)
    if asm is not None and a.genome == "auto":
        asm.to_csv(f"{out}_genomes.tsv", sep="\t", index=False)
    print(f"01_count: {len(m)} rows x {len(cols)} columns -> {out}.tsv")
    print(f"  names: {a.names}; level {a.level}; pool-informal {a.pool_informal}; SRA unit {a.sra_unit}")
    print(f"  inputs: GenBank {[str(f) for f in gb_files]}; SRA {sra_file}")
    if dropped:
        print(f"  columns not shown (add with --columns): {', '.join(dropped)}")
    print(f"  name -> row table: {out}_names.tsv")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
