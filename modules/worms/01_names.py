"""01 名称: 类群下全部名称 (各阶元, 有效+非有效) + 完整归属 + 有效名 -> names.tsv

输入: 类群名        输出: 02_原始数据/worms/names.tsv
来源: worms_taxonomy_app checklist (WoRMS AphiaChildren 递归) ; 父级/有效名/原始组合/科以上分类缺失时补查 REST.
注意: checklist 导出的是整个缓存库里的名称, 本步骤按 parent 链只保留目标子树.
用法: python3 01_names.py <Taxon>
"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import CACHE, clean, data_dir, read_tsv, summary, write_tsv, year_of
from worms import DB, REST, client

SPECIES_RANKS = {"Species", "Subspecies", "Variety", "Forma"}
RANKS = ["Kingdom", "Phylum", "Class", "Subclass", "Infraclass", "Order", "Suborder", "Family", "Subfamily",
         "Tribe", "Genus", "Subgenus", "Species", "Subspecies", "Variety", "Forma"]
LINEAGE = ["Kingdom", "Phylum", "Class", "Subclass", "Infraclass", "Order", "Suborder", "Family", "Subfamily",
           "Tribe", "Genus", "Subgenus"]


class Records:
    """AphiaID -> {name, authority, rank, status, parent}; checklist 优先, 缺的查 REST, 结果缓存在 cache/aphia_records.json."""

    def __init__(self, df):
        self.path = CACHE / "aphia_records.json"
        self.rec = json.loads(self.path.read_text()) if self.path.exists() else {}
        for r in df.itertuples():
            self.rec[r.aphia_id] = {"name": r.scientific_name, "authority": clean(r.authority), "rank": r.rank,
                                    "status": r.taxonomic_status, "parent": r.parent_id or None}
        self.http = client().http

    def _json(self, url, tries=4):
        import time
        for i in range(tries):
            try:
                return self.http.get_json(url)
            except Exception:
                if i == tries - 1:
                    self.save()
                    raise
                time.sleep(3 * (i + 1))

    def get(self, aid):
        aid = str(aid or "")
        if not aid:
            return None
        if aid not in self.rec:
            x = self._json(f"{REST}/AphiaRecordByAphiaID/{aid}")
            self.rec[aid] = x and {"name": x["scientificname"], "authority": x.get("authority"), "rank": x["rank"],
                                   "status": x["status"], "parent": str(x.get("parentNameUsageID") or "") or None}
        return self.rec[aid]

    def above_family(self, fid):
        k = f"classification:{fid}"
        if k not in self.rec:
            node, out = self._json(f"{REST}/AphiaClassificationByAphiaID/{fid}"), {}
            while node:
                out[node["rank"]] = node["scientificname"]
                node = node.get("child")
            self.rec[k] = out
        return self.rec[k]

    def lineage(self, aid):
        out, cid, seen = {}, str(aid), set()
        cur = self.get(cid)
        while cur and cid not in seen:
            seen.add(cid)
            out.setdefault(cur["rank"], cur["name"])
            if cur["rank"] == "Family":
                for k, v in self.above_family(cid).items():
                    out.setdefault(k, v)
                break
            cid = cur["parent"]
            cur = self.get(cid) if cid else None
        return out

    def save(self):
        self.path.write_text(json.dumps(self.rec, ensure_ascii=False))


def checklist(taxon, out):
    """调用 worms_taxonomy_app checklist, 只保留 parent 链能到达目标的行."""
    cmd = [sys.executable, "-m", "worms_taxonomy_app", "checklist", "--taxon", taxon, "--include-unaccepted",
           "--db", str(DB), "--output", str(out), "--prefix", "_checklist", "--delay", "0.1"]
    with open(out / "_checklist.log", "w") as fh:
        rc = subprocess.run(cmd, cwd="/mnt/n/codex/WORMS", stdout=fh, stderr=subprocess.STDOUT).returncode
    d = read_tsv(out / "_checklist_checklist.tsv")
    if rc:
        raise SystemExit(f"checklist 失败, 见 {out / '_checklist.log'}")
    root = d[(d.scientific_name == taxon) & (d.taxonomic_status == "accepted")].aphia_id
    if root.empty:
        raise SystemExit(f"WoRMS 中找不到有效名 {taxon}")
    root, parent, memo = root.iloc[0], dict(zip(d.aphia_id, d.parent_id)), {}

    def inside(a, depth=0):
        if a == root:
            return True
        if a in memo or depth > 30 or a not in parent:
            return memo.get(a, False)
        memo[a] = inside(parent[a], depth + 1)
        return memo[a]
    for f in out.glob("_checklist_*.tsv"):
        f.unlink()
    return d[d.aphia_id.map(inside)].copy()


def main(taxon):
    out = data_dir(taxon, "worms")
    d = checklist(taxon, out)
    R = Records(d)
    rows = []
    for r in d.itertuples():
        own = R.lineage(r.aphia_id)
        own.pop(r.rank, None)
        vid = r.valid_aphia_id or ""
        v = R.get(vid) if vid else None
        vl = R.lineage(vid) if vid else {}
        oid = r.original_name_usage_id or ""
        o = R.get(oid) if oid else None
        rows.append({
            "aphia_id": r.aphia_id, "scientific_name": r.scientific_name, "authority": clean(r.authority),
            "year": year_of(r.authority), "rank": r.rank, "status": r.taxonomic_status,
            "is_valid": "Y" if r.taxonomic_status == "accepted" else "N", "unaccept_reason": clean(r.unaccept_reason),
            "valid_aphia_id": vid, "valid_name": v["name"] if v else "", "valid_authority": clean(v["authority"]) if v else "",
            "valid_rank": v["rank"] if v else "", "valid_family": vl.get("Family", ""),
            "valid_subfamily": vl.get("Subfamily", ""), "valid_genus": vl.get("Genus", ""),
            **{k.lower(): own.get(k, "") for k in LINEAGE},
            "species_epithet": r.scientific_name.split()[-1] if r.rank in SPECIES_RANKS else "",
            "original_name_aphia_id": oid, "original_name": o["name"] if o else "",
            "recombined": "Y" if clean(r.authority).startswith("(") else "",
            "lineage_path": " > ".join(own[k] for k in RANKS if k in own),
            "marine": r.is_marine, "brackish": r.is_brackish, "freshwater": r.is_freshwater,
            "terrestrial": r.is_terrestrial, "extinct": r.is_extinct,
            "worms_taxonomic_citation": clean(r.citation), "lsid": r.lsid, "url": r.url, "worms_modified": r.modified,
        })
    R.save()
    n = pd.DataFrame(rows)
    syn = n[n.is_valid == "N"].groupby("valid_aphia_id")
    n["n_synonyms"] = n.aphia_id.map(syn.size()).where(n.is_valid == "Y").fillna(0).astype(int).astype(str).replace("0", "")
    n["synonyms"] = n.aphia_id.map(syn.apply(lambda g: "; ".join(f"{a} {b}".strip() for a, b in zip(g.scientific_name, g.authority)))).where(n.is_valid == "Y").fillna("")
    # 排序: 有效名的 科>亚科>属>有效名 分组, 高阶元在前, 有效名在其异名前; 归入别科/无有效名的放最后
    lvl = {k: i for i, k in enumerate(RANKS)}
    fam = n[n["rank"] == "Family"].scientific_name.iloc[0] if (n["rank"] == "Family").any() else n.family.mode().iloc[0]
    n["_k"] = list(zip(n.valid_family.map(lambda f: 2 if not f else (0 if f == fam else 1)), n.valid_family,
                       n.valid_subfamily, n.valid_genus, n["rank"].map(lambda x: 0 if lvl.get(x, 99) <= lvl["Subgenus"] else 1),
                       n.valid_name.where(n.valid_name != "", n.scientific_name), n.is_valid.map({"Y": 0, "N": 1}), n.scientific_name))
    n = n.sort_values("_k").drop(columns="_k")
    n.insert(0, "no", range(1, len(n) + 1))
    write_tsv(n, out / "names.tsv")
    sp = n[n["rank"].isin(SPECIES_RANKS)]
    summary("01_names", [f"{taxon}: {len(n)} names; species-level {len(sp)}; accepted species {(sp['rank'].eq('Species') & sp.is_valid.eq('Y')).sum()}; "
                         f"accepted genera {(n['rank'].eq('Genus') & n.is_valid.eq('Y')).sum()}", f"-> {out / 'names.tsv'}"])


if __name__ == "__main__":
    main(sys.argv[1])
