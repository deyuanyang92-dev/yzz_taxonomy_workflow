"""12 统一文库: 库外文献 (folder='external', 散在各盘) 复制到一个目录, 按科分文件夹; 原文件不动.

  python3 12_library.py <corpus> plan    按正文科名频次定科 -> discovery 同级 library_plan.tsv (不复制)
  python3 12_library.py <corpus> replan  文字更新后 (13_zh_reocr 等) 重新定科, 科变了的在文库内移动并改 relpath
  python3 12_library.py <corpus> add     之后新入库的库外文献: 定科、复制、改 relpath, 追加到计划表 (已有不动)
  python3 12_library.py <corpus> copy    按 plan 复制 (已存在且大小相同跳过), 核对大小后 docs.relpath 改指新位置,
                                         原路径存 docs.orig_path; -> 文库/文库索引.xlsx

  目标: <backup 目录>/文库/<科 中文科名>/<原文件名>  (同名加 __2, __3)
  定科: 全文 (前 300 页) 中环节动物科名 (拉丁 + 名录中文科名; 旧科名并入现科) 与属名 (映射到科) 出现次数, 文件名命中记 20 次;
        第一名 >= 5 次且 >= 第二名 2 倍 -> 该科; 总数 >= 5 -> _综合 (动物志/名录等多科);
        只命中一个科 (原文页等短文献) -> 该科; 否则 _未定. 提及 >= 20 个科且主科占比 < 40% (全门类名录) -> _综合.
  薛整理库 (source 目录) 本就集中, 不复制. 用户 2026-10-21: 同一论文多份副本全部保留 (用户自删).
"""
import argparse
import collections
import re
import shutil
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

OLD = {"Nereidae": "Nereididae", "Ariciidae": "Orbiniidae", "Amphictenidae": "Pectinariidae",
       "Hermellidae": "Sabellariidae", "Leodicidae": "Eunicidae", "Lumbriconereidae": "Lumbrineridae",
       "Nephthydidae": "Nephtyidae", "Nephthyidae": "Nephtyidae", "Euphrosynidae": "Euphrosinidae",
       "Scalibregmidae": "Scalibregmatidae", "Chlorhaemidae": "Flabelligeridae", "Chloraemidae": "Flabelligeridae",
       "Pilargiidae": "Pilargidae", "Ammocharidae": "Oweniidae", "Polyodontidae": "Acoetidae",
       "Staurocephalidae": "Dorvilleidae", "Stauronereidae": "Dorvilleidae", "Iphitimidae": "Dorvilleidae",
       "Lysaretidae": "Oenonidae", "Arabellidae": "Oenonidae", "Disomidae": "Trochochaetidae",
       "Longosomidae": "Longosomatidae", "Spirorbidae": "Serpulidae"}
GENUS_FAMILY = {"Travisia": "Travisiidae"}
MAX_PAGES = 300
FILENAME_WEIGHT = 20
MANY_FAMILIES = 20


def vocab(disc_dir):
    """拉丁科名 (family_vocab 前 140 去非环节动物) + 名录环节/星虫/螠中文科名 -> {词: 现科拉丁名}, {拉丁: 中文}."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("tri06", Path(__file__).with_name("06_triage.py"))
    tri = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tri)
    lat = [ln.split("\t")[0] for ln in (disc_dir / "family_vocab.txt").read_text().splitlines()[:140]]
    words = {f: OLD.get(f, f) for f in lat if f not in tri.NON_ANNELID}
    cn = sqlite3.connect(ROOT / "cache" / "cn_names.sqlite")
    cn_of = {}
    for latin, c in cn.execute("SELECT latin, cn FROM names WHERE rank='Family' AND phylum IN"
                               " ('Annelida', 'Sipuncula', 'Echiura')"):
        cur = OLD.get(latin, latin)
        words[latin] = cur
        words[c] = cur
        cn_of.setdefault(cur, c)
    words.update(Travisiidae="Travisiidae", 臭海蛹科="Travisiidae")
    cn_of["Travisiidae"] = "臭海蛹科"
    # 属名 -> 所属科 (原文页、单种论文常只有属名); Travisia 按 WoRMS 现归 Travisiidae
    for genus, fam in cn.execute("SELECT latin, family FROM names WHERE rank='Genus' AND phylum IN"
                                 " ('Annelida', 'Sipuncula', 'Echiura') AND family <> ''"):
        if len(genus) >= 5:
            words[genus] = GENUS_FAMILY.get(genus, OLD.get(fam, fam))
    return words, cn_of


def ensure_col(con):
    if "orig_path" not in [r[1] for r in con.execute("PRAGMA table_info(docs)")]:
        con.execute("ALTER TABLE docs ADD COLUMN orig_path TEXT")


def assign(con, words, cn_of):
    """doc_id -> (科文件夹, 科名频次前三, 原路径, 大小): 按正文 + 文件名中的科名/属名频次定科."""
    pat = re.compile("|".join(sorted(map(re.escape, words), key=len, reverse=True)))
    res = {}
    for doc_id, path, size in con.execute("SELECT doc_id, coalesce(orig_path, relpath), size FROM docs"
                                          " WHERE folder='external' ORDER BY doc_id").fetchall():
        cnt = collections.Counter()
        for (t,) in con.execute("SELECT text FROM pages WHERE doc_id=? AND page_no<=?", (doc_id, MAX_PAGES)):
            cnt.update(words[m] for m in pat.findall(t or ""))
        for m in pat.findall(Path(path).name):  # 文件名命中: 强证据 (扫描原文页常无文字)
            cnt[words[m]] += FILENAME_WEIGHT
        tot = sum(cnt.values())
        top, n = cnt.most_common(1)[0] if cnt else ("", 0)
        second = cnt.most_common(2)[1][1] if len(cnt) > 1 else 0
        if len(cnt) >= MANY_FAMILIES and n < 0.4 * tot:  # 全门类名录 (《中国海洋生物名录》曾被归龙介虫科); 专科论文
            # 在系统发育分析中也会提到 20+ 科, 但主科占比高 (Pleijel 1998 Hesionidae), 不归综合
            fam = "_综合"
        else:
            fam = top if n >= 5 and n >= 2 * second else "_综合" if tot >= 5 else top if n >= 1 and not second else "_未定"
        folder = f"{fam} {cn_of.get(fam, '')}".strip() if not fam.startswith("_") else fam
        res[doc_id] = (folder, "; ".join(f"{k} {v}" for k, v in cnt.most_common(3)), path, size)
    return res


def plan(corpus):
    cfg = litdb.corpus_cfg(corpus)
    disc_dir = Path(cfg["db"]).parent / "discovery"
    words, cn_of = vocab(disc_dir)
    con = litdb.connect(corpus)
    ensure_col(con)
    df = pd.DataFrame([{"doc_id": d, "orig_path": path, "size": size, "folder": folder, "top3": top3}
                       for d, (folder, top3, path, size) in assign(con, words, cn_of).items()])
    lib = Path(cfg["backup"]) / "文库"
    used = collections.Counter()
    targets = []
    for r in df.itertuples():
        name = Path(r.orig_path).name
        key = (r.folder, name.lower())
        used[key] += 1
        if used[key] > 1:
            name = f"{Path(name).stem}__{used[key]}{Path(name).suffix}"
        targets.append(str(lib / r.folder / name))
    df["new_path"] = targets
    out = disc_dir.parent / "library_plan.tsv"
    df.to_csv(out, sep="\t", index=False)
    vc = df.folder.value_counts()
    return [f"库外文献 {len(df)} 篇 -> {lib}", f"科文件夹 {len(vc)} 个; 最多: " +
            ", ".join(f"{k} {v}" for k, v in vc.head(8).items()), f"计划 -> {out} (未复制; 确认后跑 copy)"]


def replan(corpus):
    """文字更新后 (如 13_zh_reocr) 重新定科; 科变了的文件在文库内移动, docs.relpath 跟着改. 原文件不动."""
    cfg = litdb.corpus_cfg(corpus)
    disc_dir = Path(cfg["db"]).parent / "discovery"
    plan_f = disc_dir.parent / "library_plan.tsv"
    df = pd.read_csv(plan_f, sep="\t")
    words, cn_of = vocab(disc_dir)
    con = litdb.connect(corpus)
    new = assign(con, words, cn_of)
    lib = Path(cfg["backup"]) / "文库"
    moved = []
    for i, r in df.iterrows():
        folder, top3, _, _ = new.get(r.doc_id, (r.folder, r.top3, None, None))
        df.at[i, "top3"] = top3
        if folder == r.folder:
            continue
        old = Path(r.new_path)
        dst = lib / folder / old.name
        k = 2
        while dst.exists():
            dst = lib / folder / f"{old.stem}__{k}{old.suffix}"
            k += 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), dst)
        con.execute("UPDATE docs SET relpath=? WHERE doc_id=? AND relpath=?", (str(dst), int(r.doc_id), str(old)))
        moved.append(f"{old.name}: {r.folder} -> {folder}")
        df.at[i, "folder"], df.at[i, "new_path"] = folder, str(dst)
    con.commit()
    con.close()
    df.to_csv(plan_f, sep="\t", index=False)
    write_index(cfg, df)
    for d in lib.iterdir():  # 移空的科文件夹
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return [f"重新定科: 移动 {len(moved)} 篇"] + moved[:15] + [f"备份 -> {litdb.backup(corpus)}"]


def add(corpus):
    """新入库的库外文献 (不在 library_plan.tsv) -> 定科、复制、改 relpath, 追加到计划表; 已有文件不动."""
    cfg = litdb.corpus_cfg(corpus)
    disc_dir = Path(cfg["db"]).parent / "discovery"
    plan_f = disc_dir.parent / "library_plan.tsv"
    df = pd.read_csv(plan_f, sep="\t")
    words, cn_of = vocab(disc_dir)
    con = litdb.connect(corpus)
    ensure_col(con)
    lib = Path(cfg["backup"]) / "文库"
    have = set(df.doc_id)
    rows = []
    for d, (folder, top3, path, size) in assign(con, words, cn_of).items():
        if d in have:
            continue
        src = Path(path)
        if not src.exists():
            continue
        dst = lib / folder / src.name
        k = 2
        while dst.exists():
            dst = lib / folder / f"{src.stem}__{k}{src.suffix}"
            k += 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if dst.stat().st_size != src.stat().st_size:
            continue
        con.execute("UPDATE docs SET orig_path=coalesce(orig_path, relpath), relpath=? WHERE doc_id=?", (str(dst), d))
        rows.append({"doc_id": d, "orig_path": path, "size": size, "folder": folder, "top3": top3, "new_path": str(dst)})
    con.commit()
    df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    df.to_csv(plan_f, sep="\t", index=False)
    write_index(cfg, df)
    return [f"新增复制 {len(rows)} 篇到文库", f"备份 -> {litdb.backup(corpus)}"]


def write_index(cfg, df):
    idx = Path(cfg["backup"]) / "文库" / "文库索引.xlsx"
    df.rename(columns={"folder": "科", "orig_path": "原路径", "new_path": "文库路径", "top3": "科名频次前三"}).to_excel(
        idx, index=False)
    return idx


def copy(corpus):
    cfg = litdb.corpus_cfg(corpus)
    df = pd.read_csv(Path(cfg["db"]).parent / "library_plan.tsv", sep="\t")
    con = litdb.connect(corpus)
    ensure_col(con)
    done = skipped = bad = 0
    for i, r in enumerate(df.itertuples(), 1):
        src, dst = Path(r.orig_path), Path(r.new_path)
        if not src.exists():
            bad += 1
            continue
        if not (dst.exists() and dst.stat().st_size == src.stat().st_size):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        else:
            skipped += 1
        if dst.stat().st_size != src.stat().st_size:
            bad += 1
            continue
        con.execute("UPDATE docs SET orig_path=coalesce(orig_path, relpath), relpath=? WHERE doc_id=?",
                    (str(dst), r.doc_id))
        done += 1
        if i % 100 == 0:
            con.commit()
            print(f"  {i}/{len(df)}", flush=True)
    con.commit()
    con.close()
    idx = write_index(cfg, df)
    return [f"复制并改指 {done} 篇 (其中已存在跳过 {skipped}); 失败/源缺失 {bad}", f"索引 -> {idx}",
            f"备份 -> {litdb.backup(corpus)}"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("step", choices=["plan", "copy", "replan", "add"])
    a = ap.parse_args()
    summary(f"12_library {a.step}", {"plan": plan, "copy": copy, "replan": replan, "add": add}[a.step](a.corpus))


if __name__ == "__main__":
    main()
