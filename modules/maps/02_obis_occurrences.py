"""02 OBIS 分布记录图 (与 WoRMS 模式产地图分开): 类群全部 OBIS occurrence -> 世界地图

输入: projects/<Taxon>/02_原始数据/occurrences/obis.tsv (occurrences 模块 01_obis)
输出: projects/<Taxon>/05_图表/maps/<Taxon>_OBIS_occurrences.png / .pdf
说明: OBIS 记录 = 各数据集上传的出现记录 (调查/标本馆/文献), 不是模式产地; 未做 obistools 式质量过滤
      (陆地点、重复、离群), 仅为初步概览. 质控步骤列为 occurrences 模块计划.
用法: python3 02_obis_occurrences.py <Taxon>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import pandas as pd
from common import TODAY, data_dir, project, read_tsv, summary


def main(taxon):
    o = read_tsv(data_dir(taxon, "occurrences") / "obis.tsv")
    out = project(taxon) / "05_图表" / "maps"
    out.mkdir(parents=True, exist_ok=True)
    lat, lon = pd.to_numeric(o.latitude, errors="coerce"), pd.to_numeric(o.longitude, errors="coerce")
    ok = lat.notna() & lon.notna()
    fig = plt.figure(figsize=(14, 7.5))
    ax = plt.axes(projection=ccrs.Robinson(central_longitude=150))
    ax.set_global()
    ax.add_feature(cfeature.LAND, facecolor="#e6e6e6", edgecolor="none")
    ax.add_feature(cfeature.COASTLINE, linewidth=0.3, edgecolor="#888888")
    ax.gridlines(linewidth=0.3, color="#cccccc")
    ax.scatter(lon[ok], lat[ok], s=1.2, c="#d62728", alpha=0.35, linewidths=0, transform=ccrs.PlateCarree())
    ax.set_title(f"OBIS occurrence records of {taxon} ({ok.sum():,} records, {o.aphia_id[ok].nunique()} taxa, "
                 f"{o.dataset_id[ok].nunique()} datasets; OBIS, {TODAY})", fontsize=11)
    fig.text(0.5, 0.04, "Occurrence records as published in OBIS (surveys, collections, literature); not type localities; "
             "no quality filtering applied (preliminary).", ha="center", fontsize=8)
    import datetime
    for ext in ("png", "pdf"):
        target = out / f"{taxon}_OBIS_occurrences.{ext}"
        try:
            open(target, "ab").close()
        except PermissionError:  # 文件在别的程序中打开 -> 另存
            target = target.with_name(f"{target.stem}_{datetime.datetime.now():%H%M}{target.suffix}")
        fig.savefig(target, dpi=300, bbox_inches="tight")
    summary("maps/02", [f"{ok.sum()} OBIS records plotted", f"-> {out / (taxon + '_OBIS_occurrences.png')}"])


if __name__ == "__main__":
    main(sys.argv[1])
