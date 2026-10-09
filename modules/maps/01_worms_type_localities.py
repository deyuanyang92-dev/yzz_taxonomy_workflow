"""01 WoRMS 模式产地分布图: 有效种的模式产地坐标 (来自 worms 模块 14_coordinates) -> 世界地图

输入: projects/<Taxon>/02_原始数据/worms/names.tsv, coordinates.tsv
输出: projects/<Taxon>/05_图表/maps/<Taxon>_WoRMS_type_localities.png / .pdf
      projects/<Taxon>/05_图表/maps/<Taxon>_WoRMS_type_localities_points.tsv  (作图源数据)
符号 (同臭海蛹 Fig. 1 的 original/approximate 区分):
  ●  实心   original     坐标由原始资料给出 (标本页 / 文本中坐标)
  ○  空心   approximate  按地名定位的中心点 (Medium: 地点级)
  ·  灰色小点 approximate Low: 州省/水体/EEZ/海区中心点 (只示意大致海域)
颜色 = 亚科. 只画有效种 (accepted species); 无坐标者不画, 数量写在图注.
用法: python3 01_worms_type_localities.py <Taxon>
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
from common import TODAY, data_dir, project, read_tsv, summary, write_tsv


def main(taxon):
    src = data_dir(taxon, "worms")
    out = project(taxon) / "05_图表" / "maps"
    out.mkdir(parents=True, exist_ok=True)
    n = read_tsv(src / "names.tsv")
    c = read_tsv(src / "coordinates.tsv")
    acc = n[(n["rank"] == "Species") & (n.is_valid == "Y")][["aphia_id", "scientific_name", "authority", "subfamily"]]
    p = acc.merge(c.drop(columns=["scientific_name"]), on="aphia_id", how="left")
    have = p[p.coord_lat != ""].copy()
    have["lat"], have["lon"] = have.coord_lat.astype(float), have.coord_lon.astype(float)
    have["symbol"] = ["original" if pr == "original" else ("approximate-low" if cf == "Low" else "approximate")
                      for pr, cf in zip(have.coord_precision, have.coord_confidence)]
    write_tsv(have.drop(columns=["lat", "lon"]), out / f"{taxon}_WoRMS_type_localities_points.tsv")

    subs = sorted(x for x in have.subfamily.unique() if x) + ([""] if (have.subfamily == "").any() else [])
    cmap = plt.get_cmap("tab20", max(len(subs), 1))
    col = {s: cmap(i) for i, s in enumerate(subs)}
    fig = plt.figure(figsize=(14, 7.5))
    ax = plt.axes(projection=ccrs.Robinson(central_longitude=150))
    ax.set_global()
    ax.add_feature(cfeature.LAND, facecolor="#e6e6e6", edgecolor="none")
    ax.add_feature(cfeature.COASTLINE, linewidth=0.3, edgecolor="#888888")
    ax.gridlines(linewidth=0.3, color="#cccccc")
    pc = ccrs.PlateCarree()
    low = have[have.symbol == "approximate-low"]
    ax.scatter(low.lon, low.lat, s=6, c="#9e9e9e", alpha=0.6, transform=pc, zorder=2, linewidths=0)
    for s_ in subs:
        g = have[have.subfamily == s_]
        a = g[g.symbol == "approximate"]
        o = g[g.symbol == "original"]
        ax.scatter(a.lon, a.lat, s=22, facecolors="none", edgecolors=[col[s_]], linewidths=0.9, transform=pc, zorder=3)
        ax.scatter(o.lon, o.lat, s=22, c=[col[s_]], edgecolors="k", linewidths=0.3, transform=pc, zorder=4,
                   label=f"{s_ or 'subfamily unassigned'} ({len(g[g.symbol != 'approximate-low'])})")
    leg1 = ax.legend(loc="lower left", fontsize=7, title="Subfamily (n, excl. low-precision)", title_fontsize=7, ncol=2, frameon=True)
    ax.add_artist(leg1)
    from matplotlib.lines import Line2D
    h = [Line2D([], [], marker="o", ls="", mfc="#555", mec="k", label=f"original coordinates ({(have.symbol == 'original').sum()})"),
         Line2D([], [], marker="o", ls="", mfc="none", mec="#555", label=f"approximate: georeferenced place ({(have.symbol == 'approximate').sum()})"),
         Line2D([], [], marker="o", ls="", ms=3, mfc="#9e9e9e", mec="none", label=f"approximate (low): region/EEZ/sea centroid ({len(low)})")]
    ax.legend(handles=h, loc="lower right", fontsize=7, frameon=True)
    ax.set_title(f"Type localities of accepted species of {taxon} (WoRMS, {TODAY})", fontsize=11)
    fig.text(0.5, 0.04, f"{len(have)} of {len(acc)} accepted species plotted; {len(acc) - len(have)} without any geographic information in WoRMS. "
             "Coordinates: WoRMS specimen/type data; approximate points are centres of named places.", ha="center", fontsize=8)
    import datetime
    for ext in ("png", "pdf"):
        target = out / f"{taxon}_WoRMS_type_localities.{ext}"
        try:
            open(target, "ab").close()
        except PermissionError:  # 文件在别的程序中打开 -> 另存
            target = target.with_name(f"{target.stem}_{datetime.datetime.now():%H%M}{target.suffix}")
        fig.savefig(target, dpi=300, bbox_inches="tight")
    summary("maps/01", [f"{len(have)}/{len(acc)} accepted species plotted: original {(have.symbol == 'original').sum()}, "
                        f"approximate {(have.symbol == 'approximate').sum()}, low {len(low)}",
                        f"-> {out / (taxon + '_WoRMS_type_localities.png')}"])


if __name__ == "__main__":
    main(sys.argv[1])
