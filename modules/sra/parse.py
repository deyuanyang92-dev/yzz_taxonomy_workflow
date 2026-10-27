"""NCBI 响应的纯解析函数 (无网络, 便于离线测试)."""
import csv
import io


def parse_runinfo(text):
    """SraRunInfo CSV -> [dict]; 去 BOM、空行和重复表头行 (分页拼接/网页导出常见)."""
    text = text.lstrip("﻿")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        run = (r.get("Run") or "").strip()
        if run and run != "Run":
            rows.append({k.lstrip("﻿"): (v or "") for k, v in r.items() if k is not None})
    return rows
