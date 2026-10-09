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


def client(delay=0.05):
    """每个线程各建一个 (sqlite 连接不跨线程)."""
    return WoRMSClient(CachedHttpClient(DB, delay_seconds=delay))


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


def source_details(source_id):
    """sourcedetails 页 -> 结构化文献字段 (Authors/Year/Title/Journal/Suffix/DOI/LSID/Link/...)."""
    page = client().source_details_html(int(source_id))
    d = label_pairs(page)
    d["_open_access"] = "Y" if 'alt="OpenAccess publication"' in (page or "") else ""
    return d
