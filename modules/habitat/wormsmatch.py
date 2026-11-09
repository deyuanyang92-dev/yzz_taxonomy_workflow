"""名称 -> WoRMS 有效名、科、目、环境标记 (checklist 各步共用).

match(names) 对每个名称返回 dict:
  worms_query, worms_match_type, worms_aphia_id, worms_status, worms_unaccept_reason,
  accepted_aphia_id, accepted_name, accepted_authority, class, order, family, genus,
  is_marine, is_brackish, is_freshwater, is_terrestrial, worms_url, worms_note
非正式名 (sp. / indet.) 只按属或科取归属, 不给有效名.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from worms import REST, client, pmap  # noqa: E402

FIELDS = ["worms_query", "worms_match_type", "worms_aphia_id", "worms_status", "worms_unaccept_reason",
          "accepted_aphia_id", "accepted_name", "accepted_authority", "class", "subclass", "infraclass", "order", "family",
          "genus", "lineage",
          "is_marine", "is_brackish", "is_freshwater", "is_terrestrial", "worms_url", "worms_note"]


def query_name(name):
    """'Namalycastis abiuma (Grube)' -> 'Namalycastis abiuma'; informal names -> genus (or family) only."""
    n = re.sub(r"[‘’'\"].*?[‘’'\"]", "", name).strip()
    n = re.sub(r"\s+species group$", "", n)
    words = n.split()
    if len(words) < 2 or words[1] in ("sp.", "cf.", "nr.", "indet.", "spp."):
        return words[0], True
    out = [words[0]]
    for i, w in enumerate(words[1:], 1):
        if i == 1 and re.fullmatch(r"\([A-Z][a-z]+\)", w):      # subgenus directly after the genus
            out.append(w)
            continue
        if re.fullmatch(r"[a-zæ][a-zæ\-]+", w) and w not in ("de", "van", "von", "da", "in", "et"):
            out.append(w)
        else:
            break
    return " ".join(out), False


def fresh_json(url, params=None):
    """Direct request without the shared cache (the cache may hold an empty body from a failed call)."""
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    for i in range(4):
        try:
            with urllib.request.urlopen(full, timeout=60) as r:
                t = r.read().decode()
            return json.loads(t) if t.strip() else None
        except urllib.error.HTTPError as e:
            if e.code in (204, 404):
                return None
            time.sleep(3 * (i + 1))
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def _get(c, url, params=None):
    x = c.http.get_json(url, params=params)
    return x if x else fresh_json(url, params)


def _classification(c, aid):
    node = _get(c, f"{REST}/AphiaClassificationByAphiaID/{aid}")
    out, path = {}, []
    while node:
        out[node["rank"]] = node["scientificname"]
        path.append(node["scientificname"])
        node = node.get("child")
    out["_lineage"] = " > ".join(path)
    return out


def _pick(recs):
    """Prefer an Annelida record; exact match; accepted."""
    recs = [r for r in recs or [] if r]
    if not recs:
        return None
    def score(r):
        return ((r.get("phylum") == "Annelida") * 4 + (r.get("match_type") == "exact") * 2
                + (r.get("status") == "accepted"))
    return max(recs, key=score)


def match_one(name):
    q, informal = query_name(name)
    c = client()
    out = {f: "" for f in FIELDS}
    out["worms_query"] = q
    recs = _get(c, f"{REST}/AphiaRecordsByMatchNames",
                           params=[("scientificnames[]", q), ("marine_only", "false"), ("extant_only", "false")])
    r = _pick(recs[0] if recs else None)
    if not r:
        out["worms_note"] = "no WoRMS match"
        return out
    vid = r.get("valid_AphiaID") or r["AphiaID"]
    v = r if vid == r["AphiaID"] else _get(c, f"{REST}/AphiaRecordByAphiaID/{vid}")
    cl = _classification(c, vid)
    out.update({
        "worms_match_type": r.get("match_type", ""), "worms_aphia_id": r["AphiaID"], "worms_status": r.get("status", ""),
        "worms_unaccept_reason": r.get("unacceptreason") or "",
        "class": cl.get("Class", ""), "subclass": cl.get("Subclass", ""), "infraclass": cl.get("Infraclass", ""),
        "order": cl.get("Order", ""), "family": cl.get("Family", ""),
        "genus": cl.get("Genus", ""), "lineage": cl.get("_lineage", ""),
        "is_marine": v.get("isMarine"), "is_brackish": v.get("isBrackish"), "is_freshwater": v.get("isFreshwater"),
        "is_terrestrial": v.get("isTerrestrial"),
        "worms_url": f"https://www.marinespecies.org/aphia.php?p=taxdetails&id={vid}",
    })
    if informal:
        out["worms_note"] = f"informal name; classification from {r.get('rank', '')} {q}"
    else:
        out.update({"accepted_aphia_id": vid, "accepted_name": v.get("scientificname", ""),
                    "accepted_authority": v.get("authority") or ""})
        if r.get("match_type") != "exact":
            out["worms_note"] = f"fuzzy match ({r.get('match_type')}): {r.get('scientificname')}"
    if r.get("phylum") and r.get("phylum") != "Annelida":
        out["worms_note"] = (out["worms_note"] + "; " if out["worms_note"] else "") + f"!! phylum {r.get('phylum')}"
    for k in ("is_marine", "is_brackish", "is_freshwater", "is_terrestrial"):
        out[k] = "" if out[k] is None else str(int(out[k]))
    return out


def match(names, workers=3):
    names = list(names)
    res = pmap(match_one, names, workers=workers)
    for i, r in enumerate(res):          # sequential retry (sqlite cache contention under threads)
        if r is None:
            try:
                res[i] = match_one(names[i])
            except Exception as e:
                res[i] = {**{f: "" for f in FIELDS}, "worms_note": f"lookup error: {e}"[:200]}
    return res
