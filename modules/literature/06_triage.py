"""06 分拣 03_discover 判 review 的候选 (MORPH 1-2 种 或 FAM >= 3 种, 混有生态/线粒体组/昆虫/甲壳类论文).

  python3 06_triage.py <corpus> rules [--workers N]   规则初筛 -> discovery/triage.tsv + 子代理批次 triage_batches/
  python3 06_triage.py <corpus> merge                 合并子代理判定 triage_batches/*.out.tsv -> candidates.tsv

  规则 (前 8 页文字 + 文件名; 无文字层 OCR 前 2 页):
    TAXO = 分类学标记 (sp. nov.、holotype、material examined、synonym、新种、检索表 ...) 命中种类数
    GROUP = 环节动物类群词 (polychaet、annelid、sipuncul、多毛、星虫 ...) 种类数 + 环节动物科名种类数
    GROUP == 0 且 MORPH == 0 -> exclude (只命中非环节动物科)
    其余                     -> agent (子代理读首页判断)
  不设规则 include: 抽查 (2026-10-21) TAXO>=3 桶混有基金申请书、线粒体组; GROUP==0 但有 MORPH 的含 Leidy 1855 等老文献原文页
  merge: 子代理判 include 的, candidates.tsv decision 改为 include (原判定记入 triage 列), 之后重跑 05_ingest.
"""
import argparse
import importlib.util
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

_spec = importlib.util.spec_from_file_location("disc03", Path(__file__).with_name("03_discover.py"))
disc = importlib.util.module_from_spec(_spec)
sys.modules["disc03"] = disc  # 子进程 pickle 函数需按模块名找到
_spec.loader.exec_module(disc)

TAXO = [r"sp\.\s*nov", r"\bn\.\s*sp\b", r"nov\.\s*sp", r"gen\.\s*nov", r"new species", r"new genus", r"new record",
        r"redescri", r"holotype", r"paratype", r"syntype", r"neotype", r"lectotype", r"type locality",
        r"material examined", r"diagnosis", r"synonym", r"key to (the )?(species|genera)", r"neue art",
        r"esp[eè]ce nouvelle", r"nouvelle esp[eè]ce", r"especie nueva", r"nueva especie", r"taxonom",
        "新种", "新记录", "检索表", "正模", "副模", "同物异名", "分类"]
GROUP = ["polychaet", "polychète", "annelid", "sipuncul", "echiur", "多毛", "环节动物", "星虫", "螠", "沙蚕"]
# family_vocab 前 140 个中的非环节动物科 (人工核对 2026-10-21); 140 名以后不用
NON_ANNELID = set("""Caprellidae Chitonidae Curculionidae Gorgonidae Chrysogorgiidae Pennatulidae Halobatidae Nymphalidae
Coccosphaeridae Carabidae Sergestidae Alcyonidae Primnoidae Noctuidae Geometridae Pyralidae Arctiidae Notodontidae
Histeridae Penaeidae Alpheidae Sphingidae Staphylinidae Coccidae Papilionidae Pentatomidae Mytilidae Lycaenidae
Cerambycidae Phasmidae Buprestidae Cyprinidae Ophiuridae Tipulidae Agaristidae Lasiocampidae Formicidae
Echinidae""".split())
BATCH = 120


def signals(args):
    path, fams = args
    try:
        t, n, how = disc.text_of(path)
    except Exception as e:
        return {"path": path, "error": str(e)[:200]}
    low = (Path(path).name + "\n" + t).lower()
    taxo = [p for p in TAXO if re.search(p, low)]
    group = [g for g in GROUP if g in low] + [f for f in fams if f.lower() in low]
    return {"path": path, "n_taxo": len(taxo), "n_group": len(group), "taxo": ";".join(taxo),
            "group": ";".join(group[:12]), "head": re.sub(r"\s+", " ", t[:1500]), "error": ""}


def rules(disc_dir, workers):
    cand = pd.read_csv(disc_dir / "candidates.tsv", sep="\t")
    rev = cand[cand.decision == "review"]
    vocab = [ln.split("\t")[0] for ln in (disc_dir / "family_vocab.txt").read_text().splitlines()[:140]]
    fams = [f for f in vocab if f not in NON_ANNELID]
    with ProcessPoolExecutor(workers) as ex:
        sig = pd.DataFrame(ex.map(signals, [(p, fams) for p in rev.path], chunksize=8))
    out = rev[["path", "pages", "n_morph"]].merge(sig, on="path")
    out["rule"] = "agent"
    out.loc[(out.n_group == 0) & (out.n_morph == 0), "rule"] = "exclude"
    out.loc[out.error.fillna("") != "", "rule"] = "error"
    out.to_csv(disc_dir / "triage.tsv", sep="\t", index=False)

    bdir = disc_dir / "triage_batches"
    bdir.mkdir(exist_ok=True)
    ag = out[out.rule == "agent"].reset_index(drop=True)
    cols = ["path", "pages", "taxo", "group", "head"]
    for i in range(0, len(ag), BATCH):
        ag.loc[i:i + BATCH - 1, cols].to_csv(bdir / f"b{i // BATCH:02d}.tsv", sep="\t", index=False)
    return [f"review {len(rev)} 篇 -> 规则: {out.rule.value_counts().to_dict()}",
            f"-> {disc_dir / 'triage.tsv'}; 子代理批次 {-(-len(ag) // BATCH)} 个 -> {bdir}"]


def merge(disc_dir):
    cand = pd.read_csv(disc_dir / "candidates.tsv", sep="\t")
    tri = pd.read_csv(disc_dir / "triage.tsv", sep="\t")
    final = dict(zip(tri.path, tri.rule))
    # 子代理批次结果, 再由复核结果 (sonnet 读前 8 页, 2026-10-21) 覆盖
    outs = sorted((disc_dir / "triage_batches").glob("*.out.tsv")) + sorted(disc_dir.glob("triage_recheck.out.tsv"))
    for f in outs:
        for r in pd.read_csv(f, sep="\t").itertuples():
            final[r.path] = "include" if str(r.verdict).strip().lower() == "include" else "exclude"
    left = sum(v == "agent" for v in final.values())
    if "triage" not in cand:
        cand["triage"] = ""
    m = cand.path.isin(final) & (cand.decision == "review")
    cand.loc[m, "triage"] = cand.loc[m, "path"].map(final)
    cand.loc[m & (cand.triage == "include"), "decision"] = "include"
    cand.to_csv(disc_dir / "candidates.tsv", sep="\t", index=False)
    return [f"合并子代理结果 {len(outs)} 个文件; 仍未判 {left} 篇",
            f"review -> include {int((m & (cand.triage == 'include')).sum())} 篇; 重跑 05_ingest 入库"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("step", choices=["rules", "merge"])
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    disc_dir = Path(litdb.corpus_cfg(a.corpus)["db"]).parent / "discovery"
    summary(f"06_triage {a.step}", rules(disc_dir, a.workers) if a.step == "rules" else merge(disc_dir))


if __name__ == "__main__":
    main()
