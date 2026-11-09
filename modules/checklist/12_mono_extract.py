"""12 专著逐种抽取: OCR 页文本 -> 物种 × 采集地表 -> mono_localities.tsv

输入: 02_原始数据/checklist/ocr/<pid>/p*.txt (11 步), config.json 的 "monographs" 段,
      02_原始数据/worms/names.tsv (该类群全部 WoRMS 名称, 用于修复 OCR 粘连的拉丁名; 可缺)
输出: 02_原始数据/checklist/mono_localities.tsv, 每种 1-2 行:
      采集地类型 = 研究标本 ("标本采集地"段) / 文献记载分布 ("地理分布"段)
规则 (用户 2026-10-10 示例: CN01 (24) 突齿沙蚕):
  采集地 = 段首到第一个"。"; note = 该段其余说明 (到下一个小标题前). 原文照录, 缺失留空.
  学名: RapidOCR 会丢空格 -> 依次用 WoRMS 名称字典 / tesseract 文本 (kb.db) 修复, 都失败则标 parse_flag.
用法: python3 12_mono_extract.py <Taxon>
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
import pandas as pd  # noqa: E402
from common import data_dir, read_tsv, summary, write_tsv  # noqa: E402

KB = Path("/mnt/n/沙蚕科-知识库/kb.db")
SECTIONS = ["标本采集地", "形态特征", "地理分布", "讨论", "生态习性", "生态", "习性", "经济意义", "附记",
            "模式产地", "模式标本", "生物学", "鉴别特征", "种检索表"]
SEC_RE = re.compile(r"^(" + "|".join(SECTIONS) + r")\s*")
HEAD_RE = re.compile(r"^[(（]\s*(\d+[a-z]?)\s*[)）]\s*([一-鿿]+)\s*([A-Z].*)$")
HEAD2_RE = re.compile(r"^([\u4e00-\u9fff]{2,12}(?:[（(][\u4e00-\u9fff]{2,12}[）)])?)\s*([A-Z][a-z]+\s*(?:\([A-Z][a-z]+\)\s*)?[a-z].*?\d{4})\s*$")
GENUS_RE = re.compile(r"^\d+\.\s*[一-鿿]+属\s*[A-Z]")
FIG_RE = re.compile(r"\s*[（(〈<〔\[\s]*图\s*\d+.*$|\s*[（(〈<〔\[\s]+$")
RUNNING = re.compile(r"^(P?DC|\d{1,3}|中国动物志|环节动物门|多毛纲|Ⅱ\.?沙蚕目|[一-鿿]{1,6}[科属庙]|PDG)$")
CJK = r"[一-鿿，。、；：（）]"
LEAD_JUNK = re.compile(r"^[万丁]\s*(?=分布|为|属|系|广|本种)")   # 段首缩进被 OCR 成"万"


WATERMARK = re.compile(r"(?<=[\u4e00-\u9fff，、])P?D[CG](?=[\u4e00-\u9fff，、（])")   # 扫描水印 "PDG/DC" 混入正文


def joinlines(lines):
    out = ""
    for ln in lines:
        if out.endswith("-") and ln[:1].islower():
            out = out[:-1] + ln
        elif not out or re.match(CJK, out[-1]) or re.match(CJK, ln[0]):
            out += ln
        else:
            out += " " + ln
    return WATERMARK.sub("", out).strip()


def nospace(s):
    return re.sub(r"[^A-Za-z]", "", s).lower()


def name_dict(taxon):
    df = read_tsv(data_dir(taxon, "worms") / "names.tsv", required=False)
    if df.empty:
        return {}
    names = [n for n in df["scientific_name"] if " " in n]
    return {nospace(n): n for n in sorted(names, key=len)}


def fix_latin(glued, names, tess_line):
    """'LeonnatesdecipiensFauvel，1929' -> ('Leonnates decipiens Fauvel, 1929', flag)."""
    g = FIG_RE.sub("", glued).replace("，", ", ").replace("（", "(").replace("）", ")").strip(" ,")
    if tess_line:                                     # tesseract 保留了空格; 字母一致才用
        t = FIG_RE.sub("", tess_line).strip(" ,")
        m = re.search(r"[A-Z][a-z]+\s+(\([A-Z][a-z]+\)\s+)?[a-z].*", t)
        if m and nospace(m.group(0)) == nospace(g):
            return re.sub(r"\s*,\s*", ", ", m.group(0)).strip(" ,"), ""
    key = nospace(g)
    hit = next((names[k] for k in sorted(names, key=len, reverse=True) if key.startswith(k)), None)
    if hit:
        return attach(hit, g), ""
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z(])", " ", g)
    return re.sub(r"\s*,\s*", ", ", spaced).strip(" ,"), "学名未能用字典/tesseract 校正, 需核对空格"


def attach(binomial, g):
    """已知带空格的名称 + 粘连原串 -> 名称 + 原串中其后的命名人部分."""
    n, i, rest = len(nospace(binomial)), 0, ""
    for j, ch in enumerate(g):
        if ch.isalpha():
            i += 1
            if i == n:
                rest = g[j + 1:]
                break
    rest = re.sub(r"(?<=[a-z])(?=[A-Z(&])", " ", rest)
    rest = re.sub(r"\s*,\s*", ", ", re.sub(r"\s*\(\s*", " (", rest)).strip()
    rest = re.sub(r"\s*&\s*", " & ", rest)
    return re.sub(r"\s+", " ", (binomial + " " + rest).strip(" ,"))


def fix_from_synonymy(glued, line):
    """种标题后的异名引文行 (小字, OCR 保留空格) 若以同一名称开头, 用它补回空格."""
    g = FIG_RE.sub("", glued).replace("，", ", ").replace("（", "(").replace("）", ")").strip(" ,")
    toks = re.split(r"\s+", line.strip())
    for k in (4, 3, 2):
        cand = " ".join(toks[:k]).rstrip(":：,，.;")
        if (len(toks) >= k and re.fullmatch(r"[A-Z][a-z]+( \([A-Z][a-z]+\))?( [a-z][a-z-]+){1,2}", cand)
                and nospace(g).startswith(nospace(cand))):
            return attach(cand, g)
    return None


def tess_heads(pid):
    """kb.db tesseract 文本中的种标题行: {(page, 序号): 行}."""
    out = {}
    if not KB.exists():
        return out
    con = sqlite3.connect(KB)
    for page, text in con.execute("select page, text from pages where pid=?", (pid,)):
        for ln in (text or "").splitlines():
            m = re.match(r"^\s*[(（]\s*(\d+[a-z]?)\s*[)）]", ln)
            if m:
                out[(page, m.group(1))] = ln
    return out


def load_lines(od):
    """所有页 -> [(page, line)], 去掉页眉页码等书眉行."""
    rows = []
    for f in sorted(od.glob("p*.txt")):
        page = int(f.stem[1:])
        lines = [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
        k = 0
        while k < min(6, len(lines)) and RUNNING.match(lines[k]):
            k += 1
        rows += [(page, ln) for ln in lines[k:] if not re.fullmatch(r"\d{1,3}|PDG", ln)]
    return rows


def split_section(sec, text):
    """标本采集地: 采集地 = 段首到第一个"。", note = 其余 (用户 2026-10-10 示例).
    地理分布: 采集地 = "分布于"之后到"。" (首句多为"为热带广布种"之类概括), note = 其余句子."""
    text = LEAD_JUNK.sub("", text).strip()
    if sec == "标本采集地":
        text = re.sub(r"^地(?!中海|区|处)(?=[\u4e00-\u9fff])", "", text)    # 小标题"标本采集地"的"地"被 OCR 拆到正文行首
    if sec == "地理分布":
        m = re.search(r"分布于[：:]?(.*?)(。|$)", text)
        if m:
            note = (text[:m.start()] + text[m.end():]).strip()
            return m.group(1).strip(), note
    return split_first_sentence(text)


def split_first_sentence(text):
    i = text.find("。")
    return (text, "") if i < 0 else (text[:i].strip(), text[i + 1:].strip())


def extract(m, names):
    rows = []
    lines = load_lines(m["_dir"])
    heads = tess_heads(m["pid"])
    cur, sec, buf, buf_pages = None, None, [], set()

    def flush():
        if cur and sec == "讨论" and buf:          # 用户 2026-10-11: 讨论段文字放 note
            cur["disc"] = joinlines(buf)
            return
        if cur and sec in ("标本采集地", "地理分布") and buf:
            text = joinlines(buf)
            loc, note = split_section(sec, text)
            flags = [cur["flag"]] if cur["flag"] else []
            if len(buf_pages) > 1:
                flags.append("段落跨页, 核对是否混入图注")
            rows.append({**cur["base"], "采集地": loc, "采集地类型": "研究标本" if sec == "标本采集地" else "文献记载分布",
                         "note": note, "页码": "-".join(str(p) for p in sorted(buf_pages)),
                         "parse_flag": "; ".join(flags)})
            cur["n"] += 1

    def close_species():
        if cur and cur["n"] == 0:
            rows.append({**cur["base"], "采集地": "", "采集地类型": "", "note": "", "页码": str(cur["page"]),
                         "parse_flag": "; ".join(x for x in [cur["flag"], "未找到标本采集地/地理分布段"] if x)})
        if cur:
            for r in rows[cur["start"]:]:
                r["讨论"] = cur["disc"]

    prev = ""
    for page, ln in lines:
        h = HEAD_RE.match(ln)
        h2 = None if h else HEAD2_RE.match(ln)
        if h2 and (re.search(r"[属科]$", h2.group(1)) or "模式种" in prev):
            h2 = None
        prev = ln
        if (h and not re.search(r"[：:]\s*\d", ln)) or h2:
            flush()
            close_species()
            num, zh, lat = h.groups() if h else ("", re.sub(r"[（(].*", "", h2.group(1)), h2.group(2))
            latin, flag = fix_latin(lat, names, heads.get((page, num), ""))
            latin = re.sub(r"^(.*?\d{4}\)?).*$", r"\1", latin)      # 年份后的图号残留 "(—§ 177)" "【" 等
            if not re.search(r"(蚕|虫|蠋|蛹|蠶)$", zh):
                flag = "; ".join(x for x in [flag, "中文名疑 OCR 缺字, 核对原页"] if x)
            cur = {"page": page, "n": 0, "flag": flag, "start": len(rows), "disc": "",
                   "base": {"序号": num, "物种名（中文）": zh, "物种名（学名）": latin,
                            "参考文献": m["citation"], "pid": m["pid"]}}
            cur["glued"], cur["look"] = lat, 4 if flag else 0
            sec, buf, buf_pages = None, [], set()
            continue
        if cur and cur.get("look"):
            cur["look"] -= 1
            fixed = fix_from_synonymy(cur["glued"], ln)
            if fixed:
                fixed = re.sub(r"^(.*?\d{4}\)?).*$", r"\1", fixed)
                cur["base"]["物种名（学名）"], cur["flag"], cur["look"] = fixed, "", 0
        if GENUS_RE.match(ln):
            flush()
            sec, buf, buf_pages = None, [], set()
            continue
        s = SEC_RE.match(ln)
        if s and cur:
            flush()
            sec, buf, buf_pages = s.group(1), [], {page}
            rest = ln[s.end():].strip()
            if rest:
                buf.append(rest)
                if rest.endswith("。") and sec in ("标本采集地", "地理分布"):
                    flush()
                    sec, buf = None, []
            continue
        if sec == "讨论":
            buf.append(ln)
            buf_pages.add(page)
        if sec in ("标本采集地", "地理分布"):
            buf.append(ln)
            buf_pages.add(page)
            if ln.endswith("。"):              # 段落结束 (CN04 等无"形态特征"小标题, 形态描述紧随其后)
                flush()
                sec, buf = None, []
    flush()
    close_species()
    return rows


COLS = ["物种名（中文）", "物种名（学名）", "采集地", "参考文献", "页码", "采集地类型", "note", "讨论",
        "序号", "pid", "parse_flag"]


def main(taxon):
    d = data_dir(taxon, "checklist")
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8")).get("monographs", [])
    names = name_dict(taxon)
    rows = []
    for m in cfg:
        m["_dir"] = d / "ocr" / m["pid"]
        lo, _, hi = m["pages"].partition("-")
        n = len(list(m["_dir"].glob("p*.txt"))) if m["_dir"].exists() else 0
        if (m["_dir"] / "_done").exists() or n >= 0.95 * (int(hi or lo) - int(lo) + 1):
            rows += extract(m, names)
        else:
            print(f"   跳过 {m['pid']}: OCR 未完成 ({n} 页)")
    df = pd.DataFrame(rows, columns=COLS)
    # 书前种名目录页也形如 "(24) 突齿沙蚕 Leonnates indicus": 同一种正文已有记录时丢弃目录产生的空行
    key = ["pid", "序号", "物种名（中文）"]
    has = set(map(tuple, df.loc[df["采集地类型"] != "", key].values)) | set(
        map(tuple, df.loc[df["采集地类型"] != "", ["pid", "物种名（中文）"]].assign(序号="")[key].values))
    df = df[(df["采集地类型"] != "") | ~df[key].apply(tuple, axis=1).isin(has)]
    # 目录/分布表在正文之前: 每本书第一条有采集地的记录之前的空行一律丢弃; 4 位"序号"是年份句 (如 "(1933) 鉴定的...")
    pg = pd.to_numeric(df["页码"].str.split("-").str[0], errors="coerce")
    first = df[df["采集地类型"] != ""].assign(_p=pg).groupby("pid")["_p"].min()
    df = df[((df["采集地类型"] != "") | (pg >= df["pid"].map(first))) & (df["序号"].str.len() < 4)]
    write_tsv(df, d / "mono_localities.tsv")
    summary("12_mono_extract", [f"{df['序号'].nunique() if len(df) else 0} 种 / {len(df)} 行 -> {d / 'mono_localities.tsv'}",
                                f"需核对 (parse_flag) {int((df['parse_flag'] != '').sum()) if len(df) else 0} 行"])


if __name__ == "__main__":
    main(sys.argv[1])
