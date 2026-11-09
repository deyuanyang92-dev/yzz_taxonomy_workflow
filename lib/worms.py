"""WoRMS 访问与页面解析 (所有 worms 步骤共用).

- HTTP: 复用 /mnt/n/codex/WORMS/worms_taxonomy_app 的 CachedHttpClient/WoRMSClient,
        缓存库 cache/worms_cache.sqlite (跨项目共享, 重跑不重复联网).
- 页面: WoRMS 详情页 (sourcedetails / specdetails) 都是 <label>-><div> 成对字段, 用 label_pairs() 通用解析.
"""
import html as H
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from common import CACHE

sys.path.insert(0, "/mnt/n/codex/WORMS")
from worms_taxonomy_app.clients import WoRMSClient  # noqa: E402
from worms_taxonomy_app.http_client import CachedHttpClient  # noqa: E402

REST = "https://www.marinespecies.org/rest"
WEB = "https://www.marinespecies.org/aphia.php"
DB = CACHE / "worms_cache.sqlite"


REFRESH = "--refresh" in sys.argv   # yzz.py worms ... <Taxon> --refresh: 忽略缓存重新联网 (WoRMS 记录会更新)


def client(delay=0.05):
    """每个线程各建一个 (sqlite 连接不跨线程)."""
    return WoRMSClient(CachedHttpClient(DB, delay_seconds=delay, refresh=REFRESH))


def pmap(fn, items, workers=8):
    """并行 map; 单条异常返回 None, 不拖垮整批."""
    def safe(x):
        try:
            return fn(x)
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(safe, items))


def aphia_id(name):
    return client().http.get_json(f"{REST}/AphiaIDByName/{urllib.parse.quote(name)}", params={"marine_only": "false"})


def html_text(fragment):
    t = re.sub(r"<br\s*/?>", " ; ", fragment or "")
    t = H.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"\s+", " ", t).strip(" ;")
    return re.sub(r"\s*\[\s*(details|view)\s*\]?|\s*\(look up in IMIS\s*\)", "", t).strip()


def label_pairs(page):
    """WoRMS 详情页 -> {label: value}; 多行值用 ' ; ' 连接."""
    out = {}
    for lab, body in re.findall(r"<label[^>]*>(.*?)</label>\s*<div[^>]*>(.*?)</div>\s*</div>", page or "", re.S):
        lab = html_text(lab)
        if lab and lab not in ("Edit history", "Sessions", "Options", "Export"):
            out[lab] = html_text(body)
    return out


TYPE_NOTE = re.compile(r"holotype|lectotype|neotype|syntype|paratype|paralectotype|type (material|specimen|examination|series)|"
                       r"\btypes?\b|original material|from (the )?type", re.I)


def source_notes(page):
    """taxdetails 页 Sources 区 -> [{category, use, source_id, page_web, note}].
    REST AphiaSourcesByAphiaID 只给 page, 不给 note; 'page(s): 202; note: redescription from holotype' 只在网页上
    (用户 2026-11-08 发现: M. orientalis 329257, M. aegypti 1306160)."""
    page = page or ""
    i = page.find('id="sources"')
    if i < 0:
        return []
    body = page[i:]
    heads = [(m.start(), html_text(m.group(1))) for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", body, re.S)]
    ents = list(re.finditer(r'<b>([^<]{2,80})</b>\s*<span id="aphia_ct_source_(\d+)">', body))
    out = []
    for k, m in enumerate(ents):
        seg = body[m.end(): ents[k + 1].start() if k + 1 < len(ents) else m.end() + 8000]
        cut = seg.find("<small>")
        seg = seg[: cut if cut >= 0 else len(seg)]
        j = seg.find("</span>")
        after = html_text(seg[j + 7:]) if j >= 0 else ""
        pg = re.search(r"page\(s\):\s*(.*?)(?:;\s*note:|$)", after)
        note = re.search(r"note:\s*(.*)$", after)
        cat = [h for p, h in heads if p < m.start()]
        out.append({"category": cat[-1] if cat else "", "use": html_text(m.group(1)), "source_id": m.group(2),
                    "page_web": pg.group(1).strip(" ;") if pg else "", "note": note.group(1).strip(" ;") if note else ""})
    return out


def source_details(source_id):
    """sourcedetails 页 -> 结构化文献字段 (Authors/Year/Title/Journal/Suffix/DOI/LSID/Link/...)."""
    page = client().source_details_html(int(source_id))
    d = label_pairs(page)
    d["_open_access"] = "Y" if 'alt="OpenAccess publication"' in (page or "") else ""
    return d
