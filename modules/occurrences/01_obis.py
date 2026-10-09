"""01 OBIS 分布记录: 类群 (含下级) 在 OBIS 的全部 occurrence -> obis.tsv

对应 Martin et al. 2021 (Diversity 13, Phyllodocida 综述) 的 R 流程 robis::occurrence() 一步
(原脚本: /mnt/n/codex/fetch_Worms_data/data_retrieval_and_preparation.r, S. Faulwetter).
输入: 类群名 (用 WoRMS AphiaID 查询 OBIS, OBIS 分类即 WoRMS)
输出: projects/<Taxon>/02_原始数据/occurrences/obis.tsv  每行 = 一条分布记录
字段: obis_id, aphia_id (OBIS 匹配到的有效 AphiaID), scientific_name, original_scientific_name, latitude, longitude,
      coordinate_uncertainty_m, depth_m, min_depth_m, max_depth_m, event_date, year, basis_of_record, type_status,
      occurrence_status, country, locality, institution_code, catalog_number, dataset_id, flags
API: https://api.obis.org/v3/occurrence?taxonid=<AphiaID>&size=10000&after=<id>  (分页; 结果缓存 cache/obis/)
用法: python3 01_obis.py <Taxon>
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import pandas as pd
from common import CACHE, data_dir, summary, write_tsv
from worms import aphia_id

FIELDS = {"id": "obis_id", "aphiaID": "aphia_id", "scientificName": "scientific_name",
          "originalScientificName": "original_scientific_name", "decimalLatitude": "latitude", "decimalLongitude": "longitude",
          "coordinateUncertaintyInMeters": "coordinate_uncertainty_m", "depth": "depth_m", "minimumDepthInMeters": "min_depth_m",
          "maximumDepthInMeters": "max_depth_m", "eventDate": "event_date", "date_year": "year", "basisOfRecord": "basis_of_record",
          "typeStatus": "type_status", "occurrenceStatus": "occurrence_status", "country": "country", "locality": "locality",
          "institutionCode": "institution_code", "catalogNumber": "catalog_number", "dataset_id": "dataset_id", "flags": "flags"}


def get(url):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "yzz-taxonomy-workflow/0.1"}), timeout=180) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(5 * (i + 1))
    raise SystemExit(f"OBIS 请求失败: {url}")


def main(taxon):
    out = data_dir(taxon, "occurrences")
    tid = aphia_id(taxon)
    cdir = CACHE / "obis" / str(tid)
    cdir.mkdir(parents=True, exist_ok=True)
    rows, after, page = [], None, 0
    total = get(f"https://api.obis.org/v3/occurrence?taxonid={tid}&size=1")["total"]
    while True:
        page += 1
        f = cdir / f"page_{page:04d}.json"
        if f.exists():
            res = json.loads(f.read_text())
        else:
            q = {"taxonid": tid, "size": 10000, "fields": ",".join(FIELDS)}
            if after:
                q["after"] = after
            res = get("https://api.obis.org/v3/occurrence?" + urllib.parse.urlencode(q))["results"]
            f.write_text(json.dumps(res))
        if not res:
            break
        rows += res
        after = res[-1]["id"]
        print(f"  OBIS {len(rows)}/{total}", flush=True)
        if len(res) < 10000:
            break
    d = pd.DataFrame(rows).reindex(columns=list(FIELDS)).rename(columns=FIELDS)
    d["flags"] = d["flags"].map(lambda x: ";".join(x) if isinstance(x, list) else (x or ""))
    for c in ("aphia_id", "year"):
        d[c] = d[c].map(lambda v: "" if pd.isna(v) else str(int(float(v))))
    write_tsv(d, out / "obis.tsv")
    summary("01_obis", [f"{taxon} (AphiaID {tid}): {len(d)}/{total} OBIS records; taxa {d.aphia_id.nunique()}; "
                        f"with type_status {(d.type_status.fillna('') != '').sum()}",
                        f"-> {out / 'obis.tsv'}"])


if __name__ == "__main__":
    main(sys.argv[1])
