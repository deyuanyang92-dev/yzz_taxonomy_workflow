"""18 BHL 下载: BHL 页 ID -> 连续页图像 -> PDF (不需要 API key).

BHL 网页 / pagetext 对脚本返回 403, API 无 key 返回 401 (2026-11-08 实测); 但
https://www.biodiversitylibrary.org/pageimage/<pageID> 302 跳转到公开数据桶
bhl-open-data.s3.us-east-2.amazonaws.com/web/<barcode>/<barcode>_<seq>_full.webp, 同一卷后续页 seq+1, seq+2 ...
WoRMS 文献链接多为 BHL 页 (biodiversitylibrary.org/page/<id>), 可直接用.

  python3 18_bhl.py page <pageID> -n 16 -o out.pdf        从该页起连下 16 页
  python3 18_bhl.py cite <list.tsv> -o <目录>             列: name, journal, volume, year, start, end, expect (需 config/bhl.json API key)
  python3 18_bhl.py batch <list.tsv> -o <目录>            列: name, bhl_page, n_pages (可选 expect: 首页应含的词, 如作者姓)
      每篇: <目录>/<name>.pdf; 首页 tesseract OCR, 含 expect -> ok, 否则 check (WoRMS 链接可能指向种所在页而非文章首页)
      结果表 <目录>/bhl_result.tsv
注意: 只下连续页; 图版常在卷末, 不含在内 (result 里提示). bibliography/item 链接 (整本书) 不处理, 列为 manual.
"""
import argparse
import io
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (yzz-taxonomy-workflow; BHL open data)"}
PAGEIMG = "https://www.biodiversitylibrary.org/pageimage/{}"


def resolve(page_id):
    """页 ID -> (S3 前缀, 序号, 序号位数)."""
    r = requests.get(PAGEIMG.format(page_id), headers=UA, allow_redirects=False, timeout=60)
    loc = r.headers.get("Location", "")
    m = re.match(r"(.*/[^/]+_)(\d+)(_full\.\w+)$", loc)
    if not m:
        raise RuntimeError(f"pageimage {page_id}: 无跳转 ({r.status_code})")
    return m.group(1), int(m.group(2)), len(m.group(2)), m.group(3)


def fetch(page_id, n, out, start_offset=0):
    pre, seq, w, suf = resolve(page_id)
    imgs = []
    for k in range(start_offset, start_offset + n):
        url = f"{pre}{seq + k:0{w}d}{suf}"
        r = requests.get(url, headers=UA, timeout=90)
        if r.status_code != 200:
            break
        imgs.append(Image.open(io.BytesIO(r.content)).convert("RGB"))
        time.sleep(0.3)
    if not imgs:
        raise RuntimeError(f"{page_id}: 0 页")
    imgs[0].save(out, save_all=True, append_images=imgs[1:], resolution=150)
    return len(imgs), imgs[0]


def ocr(img):
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        img.save(f.name)
        try:
            return subprocess.run(["tesseract", f.name, "-", "-l", "eng+deu+fra+lat"], capture_output=True, text=True, timeout=120).stdout
        except Exception:
            return ""


API = "https://www.biodiversitylibrary.org/api3"
KEYFILE = Path(__file__).resolve().parents[2] / "config" / "bhl.json"   # {"apikey": "..."} (已 gitignore)


def api(op, **kw):
    import json
    key = json.loads(KEYFILE.read_text())["apikey"]
    r = requests.get(API, params={"op": op, "format": "json", "apikey": key, **kw}, headers=UA, timeout=90)
    j = r.json()
    if j.get("Status") != "ok":
        raise RuntimeError(f"{op}: {j.get('ErrorMessage')}")
    time.sleep(0.4)
    return j.get("Result") or []


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())


def locate(journal, volume, year, start, end):
    """期刊名 + 卷 (+年) + 起止页码 -> [pageID...] (API: 题名检索 -> 卷 -> 页码)."""
    # 检索结果 BHLType 多为 'Item' (带 TitleID), 不是 'Title' (2026-11-08 实测); 按 TitleID 去重
    seen, titles = set(), []
    for x in api("PublicationSearch", searchterm=journal, searchtype="C"):
        if x.get("TitleID") and x["TitleID"] not in seen:
            seen.add(x["TitleID"])
            titles.append(x)
    jw = set(_norm(journal).split())
    titles.sort(key=lambda x: -len(jw & set(_norm(x.get("Title")).split())))
    for t in titles[:5]:
        meta = api("GetTitleMetadata", id=t["TitleID"], items="t")
        items = meta[0].get("Items", []) if meta else []
        vol = [i for i in items if re.search(rf"(^|\D){volume}(\D|$)", f"{i.get('Volume', '')}")] if volume else []
        if year:
            vol = [i for i in vol if str(year) in f"{i.get('Volume', '')} {i.get('Year', '')}"] or vol or \
                  [i for i in items if str(year) in f"{i.get('Volume', '')} {i.get('Year', '')}"]
        for it in vol[:4]:
            pages = api("GetItemMetadata", id=it["ItemID"], pages="t")[0].get("Pages", [])
            sel = []
            for p in pages:
                nums = [re.sub(r"\D", "", n.get("Number", "")) for n in p.get("PageNumbers") or []]
                if any(n and start <= int(n) <= end for n in nums):
                    sel.append(p["PageID"])
            if sel:
                return sel, f"{t.get('Title')} | {it.get('Volume')}"
    return [], ""


def fetch_ids(page_ids, out):
    imgs = []
    for pid in page_ids:
        r = requests.get(PAGEIMG.format(pid), headers=UA, timeout=90)
        if r.status_code == 200:
            imgs.append(Image.open(io.BytesIO(r.content)).convert("RGB"))
        time.sleep(0.3)
    if not imgs:
        raise RuntimeError("0 页")
    imgs[0].save(out, save_all=True, append_images=imgs[1:], resolution=150)
    return len(imgs), imgs[0]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["page", "batch", "cite"])
    ap.add_argument("arg")
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("-o", required=True)
    a, _ = ap.parse_known_args(argv)
    if a.cmd == "page":
        k, _ = fetch(a.arg, a.n, a.o)
        print(f"[18_bhl] {k} pages -> {a.o}")
        return
    import pandas as pd
    L = pd.read_csv(a.arg, sep="\t", dtype=str).fillna("")
    out = Path(a.o)
    out.mkdir(parents=True, exist_ok=True)
    res = []
    if a.cmd == "cite":     # 列: name, journal, volume, year, start, end, expect
        for r in L.itertuples():
            try:
                ids, where = locate(r.journal, r.volume, r.year, int(r.start), int(r.end))
                if not ids:
                    raise RuntimeError("BHL 未找到该卷/页")
                k, first = fetch_ids(ids, out / f"{r.name}.pdf")
                txt = ocr(first).lower()
                exp = [e.lower() for e in r.expect.split(";") if e.strip()]
                st = "ok" if exp and all(e in txt for e in exp) else "check"
                res.append({"name": r.name, "pages": k, "status": st, "where": where, "file": str(out / f"{r.name}.pdf")})
            except Exception as e:
                res.append({"name": r.name, "pages": 0, "status": f"fail: {e}"[:150], "where": "", "file": ""})
            print(r.name, res[-1]["status"], res[-1]["pages"], res[-1]["where"][:70], flush=True)
        pd.DataFrame(res).to_csv(out / "bhl_cite_result.tsv", sep="\t", index=False)
        return
    for r in L.itertuples():
        f = out / f"{r.name}.pdf"
        try:
            k, first = fetch(r.bhl_page, int(r.n_pages or a.n), f)
            txt = ocr(first).lower()
            exp = [e.lower() for e in str(getattr(r, "expect", "")).split(";") if e.strip()]
            st = "ok" if exp and all(e in txt for e in exp) else "check"
            res.append({"name": r.name, "bhl_page": r.bhl_page, "pages": k, "status": st, "file": str(f), "first_page_ocr": txt[:300].replace("\n", " ")})
        except Exception as e:
            res.append({"name": r.name, "bhl_page": r.bhl_page, "pages": 0, "status": f"fail: {e}"[:120], "file": "", "first_page_ocr": ""})
        print(r.name, res[-1]["status"], res[-1]["pages"], flush=True)
    pd.DataFrame(res).to_csv(out / "bhl_result.tsv", sep="\t", index=False)
    print(f"[18_bhl] {sum(x['status'] == 'ok' for x in res)} ok, {sum(x['status'] == 'check' for x in res)} check, "
          f"{sum(x['status'].startswith('fail') for x in res)} fail -> {out / 'bhl_result.tsv'} (图版常在卷末, 未含)")


if __name__ == "__main__":
    main(sys.argv[1:])
