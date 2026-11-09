"""13 地名标准化 (转换层): WoRMS 模式产地记录 -> Region / Country / ISO / State/Province / County/City / Locality / Water body (英文)

输入: types.tsv, specimens.tsv (无WoRMS 模式产地记录时用标本 verbatimGeounit)
输出: 02_原始数据/worms/localities.tsv  每行 = 一个种级名称
缓存: cache/locality_norm.json (跨项目共用, 已标准化的地名不再花 token)
流程: 1) 运行本步骤 -> 缓存未命中的地名写到 cache/locality_inbox/todo_N.json
      2) 由 sonnet 子代理按 modules/worms/LOCALITY_PROMPT.md 写 done_N.json  (Claude 负责派发)
      3) 再运行本步骤 -> 并入缓存, 生成 localities.tsv
原则: 只依据 WoRMS 记录值, 不能确定留空; Confidence = High/Medium/Low (Low 需人工核对).
用法: python3 13_localities.py <Taxon>
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import CACHE, clean, data_dir, read_tsv, summary, uniq, write_tsv

FIELDS = ["Region", "Country", "ISO", "State/Province", "County/City", "Locality", "Water body", "Confidence"]
NORM, INBOX = CACHE / "locality_norm.json", CACHE / "locality_inbox"


def key(t, spec_verbatim):
    text = t.get("type_locality_text") or t.get("type_localities") or spec_verbatim or t.get("type_dist_locality") or ""
    ctx = "; ".join(uniq([t.get("type_locality_contained_in", ""), t.get("type_dist_higher_geography", "")]))
    return clean(text) + (f" || {ctx}" if ctx and text else "")


def main(taxon):
    out = data_dir(taxon, "worms")
    t = read_tsv(out / "types.tsv")
    s = read_tsv(out / "specimens.tsv", required=False)
    verb = {}
    if len(s):
        col = "worms: verbatimGeounit" if "worms: verbatimGeounit" in s else None
        for a, g in s.groupby("aphia_id"):
            verb[a] = "; ".join(uniq(g[col])) if col else ""
    norm = json.loads(NORM.read_text()) if NORM.exists() else {}
    INBOX.mkdir(parents=True, exist_ok=True)
    for f in sorted(INBOX.glob("done_*.json")):
        for k, v in json.loads(f.read_text()).items():
            norm[k] = {c: clean(v.get(c, "")) for c in FIELDS}
        f.rename(f.with_suffix(".merged"))
    NORM.write_text(json.dumps(norm, ensure_ascii=False, indent=0))

    t["locality_key"] = [key(r, verb.get(r["aphia_id"], "")) for r in t.to_dict("records")]
    todo = sorted({k for k in t.locality_key if k and k not in norm})
    for f in INBOX.glob("todo_*.json"):
        f.unlink()
    for i in range(0, len(todo), 150):
        (INBOX / f"todo_{i // 150 + 1}.json").write_text(json.dumps(todo[i:i + 150], ensure_ascii=False, indent=0))

    def row_(r):
        k, src = (r.locality_key, "WoRMS type-locality record") if r.locality_key else ("", "")
        v = norm.get(k, {})
        return {"aphia_id": r.aphia_id, "locality_source_text": k, "locality_source": src,
                **{c.lower().replace("/", "_").replace(" ", "_"): v.get(c, "") for c in FIELDS}}
    loc = pd.DataFrame([row_(r) for r in t.itertuples()])
    write_tsv(loc, out / "localities.tsv")
    n_files = -(-len(todo) // 150)
    summary("13_localities", [f"{t.locality_key.ne('').sum()} names with type-locality text; {len(set(t.locality_key) - {''})} distinct; "
                              f"cached {len(set(t.locality_key) - {''}) - len(todo)}; TODO {len(todo)} -> {n_files} files in {INBOX}",
                              "confidence: " + "; ".join(f"{k or 'blank'} {v}" for k, v in loc.confidence.value_counts().items()),
                              f"-> {out / 'localities.tsv'}" + ("   (TODO>0: dispatch sub-agents with LOCALITY_PROMPT.md, then rerun 13-19)" if todo else "")])


if __name__ == "__main__":
    main(sys.argv[1])
