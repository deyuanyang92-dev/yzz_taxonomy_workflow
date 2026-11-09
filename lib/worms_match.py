"""WoRMS 批量名称匹配 (Taxon match): 文献学名 -> AphiaID / 状态 / 现行有效名.

用法:
  python3 yzz.py match <表格.xlsx|.csv|.tsv|名单.txt> [--col 列名] [--family Nereididae] [--out 输出.xlsx]

- 学名列自动识别 (学名 / 物种名（学名） / scientificName / name ...), 也可 --col 指定; .txt 每行一个名.
- 先拆出 "属 (亚属) 种 亚种" 与命名人, 只用名称部分查询 (OCR 命名人格式不一, 影响匹配);
  不带亚属无结果时, 再带亚属重查一次.
- 接口 AphiaRecordsByMatchNames (每批 50 个), HTTP 结果缓存在 cache/worms_cache.sqlite, 重跑不重复联网.
- 输出 = 原表全部列 + 匹配列; 需人工核对的行标黄, 原因写在 check_note.
- 多个候选时: 有 --family 则优先该科, 再优先 exact; 无法唯一确定时标注, 不替用户选.
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import clean  # noqa: E402

NAME_COLS = ["学名", "物种名（学名）", "物种名(学名)", "拉丁名", "scientificName", "scientific_name",
             "ScientificName", "species", "Species", "name", "Name"]
RANK_MARKERS = {"var.", "subsp.", "ssp.", "f.", "forma"}
QUALIFIERS = {"cf.", "aff.", "cf", "aff", "sp.", "spp.", "sp", "spp", "?"}
SYNONYM_OK = {"accepted", "unaccepted", "superseded combination", "alternative representation",
              "superseded rank", "misspelling - incorrect subsequent spelling", "misspelling",
              "junior subjective synonym", "junior objective synonym", "junior synonym", "junior homonym",
              "incorrect original spelling", "original spelling", "corrected spelling"}
MATCH_COLS = ["query_name", "authority_in", "qualifier", "match_type", "matched_name", "matched_authority",
              "AphiaID", "status", "valid_name", "valid_authority", "valid_AphiaID", "name_changed", "family", "match_info",
              "n_candidates", "check_note"]


def parse_name(raw):
    """'Nereis (Neanthes) japonica Izuka, 1908' ->
    {'name': 'Nereis japonica', 'name_subgenus': 'Nereis (Neanthes) japonica', 'authority': 'Izuka, 1908', 'qualifier': ''}"""
    s = clean(raw).replace("（", "(").replace("）", ")").replace("，", ",")
    s = re.sub(r"(?<=[a-z])(cf\.|aff\.)(?=[a-z])", r" \1 ", s)          # OCR 粘连: Eusylliscf.irregulata
    s = re.sub(r"\s+", " ", s).strip(" .;,")
    toks = s.split(" ")
    out = {"name": "", "name_subgenus": "", "authority": "", "qualifier": ""}
    if not toks or not re.fullmatch(r"[A-Z][a-z]+", toks[0]):
        return out
    genus, subgenus, epithets, quals = toks[0], "", [], []
    i = 1
    while i < len(toks):
        t = toks[i]
        if not subgenus and not epithets and re.fullmatch(r"\([A-Z][a-z]+\)", t):
            subgenus = t
        elif t.lower() in QUALIFIERS:
            quals.append(t)
        elif t in RANK_MARKERS and i + 1 < len(toks) and re.fullmatch(r"[a-z][a-z-]+", toks[i + 1]):
            epithets += [t, toks[i + 1]]
            i += 1
        elif re.fullmatch(r"[a-z][a-z-]+", t) and t not in ("de", "von", "van", "et", "in", "ex", "la", "du"):
            epithets.append(t)
        else:
            break
        i += 1
    out["name"] = " ".join([genus, *epithets])
    out["name_subgenus"] = " ".join([genus, subgenus, *epithets]) if subgenus else out["name"]
    out["authority"] = " ".join(toks[i:]).strip()
    out["qualifier"] = " ".join(quals)
    return out


def pick(cands, family=""):
    """多候选时挑一个; 返回 (record|None, note)."""
    if not cands:
        return None, ""
    pool = [c for c in cands if family and (c.get("family") or "") == family] or cands
    exact = [c for c in pool if c.get("match_type") == "exact"] or pool
    note = ""
    if len({c.get("AphiaID") for c in exact}) > 1:
        note = f"{len(exact)} 个同等候选, 已取第一个"
    elif family and not [c for c in cands if (c.get("family") or "") == family]:
        note = f"候选不属 {family}"
    return exact[0], note


def _query(client, names, size=20):
    """AphiaRecordsByMatchNames 分小批查询 (长 URL 易 503), 每批失败重试 3 次."""
    import time
    out = []
    for i in range(0, len(names), size):
        batch = names[i:i + size]
        for k in range(3):
            try:
                out += client.records_by_match_names(batch, marine_only=False, extant_only=False,
                                                     match_authority=False)
                break
            except Exception:
                if k == 2:
                    raise
                time.sleep(5 * (k + 1))
    return out


def match_names(names, family="", client=None):
    """names: 原文学名列表 -> {原文学名: 匹配结果 dict (键 = MATCH_COLS)}; 同名只查一次."""
    if client is None:
        from worms import client as mk
        client = mk()
    uniq = list(dict.fromkeys(n for n in (clean(x) for x in names) if n))
    parsed = {n: parse_name(n) for n in uniq}
    queries = list(dict.fromkeys(p["name"] for p in parsed.values() if p["name"]))
    found = dict(zip(queries, _query(client, queries)))
    retry = list(dict.fromkeys(p["name_subgenus"] for p in parsed.values()
                               if p["name"] and not found.get(p["name"]) and p["name_subgenus"] != p["name"]))
    if retry:
        found.update(zip(retry, _query(client, retry)))
    # 后备 (依次尝试, 取第一个有结果的):
    #  种下名 "Perinereis nuntia var. brevicirris": 去 var. -> 属+种下加词 (变种多已提升为种, 如 P. helleri)
    #  -> 属+种 (最后手段; 2026-10-11 实测直接退回到种会给错有效名: P. nuntia var. brevicirris 的有效名是 P. vallata)
    #  OCR 粘连 "Typosyllisvittata": 试所有切分点, 取唯一精确命中 (无精确时取唯一近似命中)
    fallback = {}
    for p in parsed.values():
        if not p["name"] or found.get(p["name"]) or found.get(p["name_subgenus"]):
            continue
        toks = [t for t in p["name"].split() if t not in RANK_MARKERS]
        if len(toks) > 2:
            fallback[p["name"]] = ("infra", [" ".join(toks), f"{toks[0]} {toks[-1]}", " ".join(toks[:2])])
        elif len(toks) == 1 and len(toks[0]) >= 8:
            t = toks[0]
            fallback[p["name"]] = ("glued", [f"{t[:i]} {t[i:]}" for i in range(4, len(t) - 2)])
    qs = list(dict.fromkeys(c for _, cs in fallback.values() for c in cs if c not in found))
    if qs:
        found.update(zip(qs, _query(client, qs)))
    raw = dict(found)                          # 只用原始查询结果判断命中步骤, 不受下面回填影响
    fb_note = {}
    infra_msg = ["种下名去掉 var./f. 后匹配", "种下名在 WoRMS 以种级名称 {c} 收录", "种下名 WoRMS 无记录, 退回按种 {c} 匹配"]
    for name, (kind, cs) in fallback.items():
        if kind == "infra":
            k = next((i for i, c in enumerate(cs) if raw.get(c)), None)
            if k is not None:
                found[name] = raw[cs[k]]
                fb_note[name] = infra_msg[k].format(c=cs[k])
            continue
        hits = [c for c in cs if any(r.get("match_type") == "exact" for r in raw.get(c) or [])]
        if not hits:
            hits = [c for c in cs if raw.get(c)]
        if len(hits) == 1:
            found[name] = raw[hits[0]]
            fb_note[name] = f"OCR 粘连, 按 {hits[0]} 匹配"
    out = {}
    for n, p in parsed.items():
        cands = found.get(p["name"]) or found.get(p["name_subgenus"]) or []
        rec, note = pick(cands, family)
        row = dict.fromkeys(MATCH_COLS, "")
        row.update(query_name=p["name"], authority_in=p["authority"], qualifier=p["qualifier"],
                   n_candidates=str(len(cands)))
        fb = fb_note.get(p["name"], "")
        if fb.startswith(("种下名去掉", "种下名在 WoRMS")):   # 确定的对应关系: 只作说明, 不标黄
            row["match_info"], fb = fb, ""
        notes = [x for x in (note, fb) if x]
        if not p["name"]:
            notes.append("无法解析为学名")
        elif rec is None:
            notes.append("WoRMS 无匹配")
        else:
            row.update(match_type=rec.get("match_type") or "", matched_name=rec.get("scientificname") or "",
                       matched_authority=rec.get("authority") or "", AphiaID=str(rec.get("AphiaID") or ""),
                       status=rec.get("status") or "", valid_name=rec.get("valid_name") or "",
                       valid_authority=rec.get("valid_authority") or "",
                       valid_AphiaID=str(rec.get("valid_AphiaID") or ""), family=rec.get("family") or "")
            if row["match_type"] != "exact":
                notes.append(f"非精确匹配 ({row['match_type']}), 核对拼写/OCR")
            if row["valid_name"] and row["valid_name"] != row["matched_name"]:
                row["name_changed"] = "Y"
            if not row["valid_name"]:
                notes.append(f"状态 {row['status']}, 无有效名")
            elif row["status"] not in SYNONYM_OK:
                notes.append(f"状态 {row['status']}")
        if p["qualifier"]:
            notes.append(f"原文含 {p['qualifier']}")
        row["check_note"] = "; ".join(notes)
        out[n] = row
    return out


def needs_check(row):
    """非 exact / 无匹配 / 多候选 / 非 accepted 等 -> 标黄. 仅"异名→有效名"不算问题."""
    return bool(row.get("check_note"))


def read_table(path, sheet=None):
    path = Path(path)
    suf = path.suffix.lower()
    if suf in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=sheet or 0, dtype=str).fillna("")
    if suf in (".tsv", ".tab"):
        return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    if suf == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return pd.DataFrame({"学名": lines})


def guess_col(df, col=None):
    if col:
        if col not in df.columns:
            raise SystemExit(f"找不到列 {col!r}; 现有列: {list(df.columns)}")
        return col
    for c in NAME_COLS:
        if c in df.columns:
            return c
    raise SystemExit(f"无法自动识别学名列, 请用 --col 指定; 现有列: {list(df.columns)}")


def main(argv):
    ap = argparse.ArgumentParser(prog="yzz.py match", description="WoRMS 批量名称匹配")
    ap.add_argument("file")
    ap.add_argument("--col", help="学名所在列 (默认自动识别)")
    ap.add_argument("--sheet", help="Excel 工作表名 (默认第一个)")
    ap.add_argument("--family", default="", help="优先该科的候选, 如 Nereididae")
    ap.add_argument("--out", help="输出 .xlsx (默认 <原名>_worms.xlsx)")
    a = ap.parse_args(argv)

    df = read_table(a.file, a.sheet)
    col = guess_col(df, a.col)
    res = match_names(df[col].tolist(), a.family)
    empty = dict.fromkeys(MATCH_COLS, "")
    m = pd.DataFrame([res.get(clean(v), empty) for v in df[col]], index=df.index)
    m.columns = [f"WoRMS_{c}" if c in df.columns else c for c in m.columns]
    out_df = pd.concat([df, m], axis=1)

    from excel import YELLOW, write_workbook
    out = Path(a.out) if a.out else Path(a.file).with_name(Path(a.file).stem + "_worms.xlsx")
    out = write_workbook(out, {"worms_match": out_df},
                         shade={"worms_match": [("check_note", lambda v: bool(v), YELLOW)]})
    rows = list(res.values())
    n_syn = sum(r["name_changed"] == "Y" for r in rows)
    print(f"[match] {len(df)} 行 / {len(rows)} 个不同学名 -> {out}")
    print(f"   精确匹配 {sum(r['match_type'] == 'exact' for r in rows)}; 无匹配 {sum(not r['AphiaID'] for r in rows)}; "
          f"异名→有效名 {n_syn}; 需核对(标黄) {sum(needs_check(r) for r in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
