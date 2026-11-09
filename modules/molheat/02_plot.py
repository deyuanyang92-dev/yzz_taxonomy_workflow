"""02 plot: count matrix TSV(s) from 01_count.py -> heatmap (PDF/PNG/SVG). Same options as molheat.R.

One or more panels stacked top to bottom (e.g. genus panel + species zoom). Per-panel options take one value per
--matrix (last value repeats). Taxon names are typeset by taxname.py / name_style.json: genus and epithets italic;
sp. / cf. / aff. / und., informal codes, authors and family-level names upright.

  python3 yzz.py molheat 02 Eunicidae --matrix Eunicidae_genus.tsv --matrix Marphysa_species.tsv \\
      --label Eunicidae --label Marphysa --cmap viridis --cmap magma --vmax 200 --vmax 20 \\
      --highlight Marphysa --abbreviate-genus no --abbreviate-genus yes --out Eunicidae_heatmap

Options (defaults in brackets):
  --cmap NAME|c1,c2,...   matplotlib colormap or colour list [viridis]      --vmax auto|N (cap; ">N" on colour bar) [auto]
  --log yes|no            log colour scale [no]                             --values yes|no  numbers in cells [yes]
  --zero cross|blank|grey|zero   empty cells [cross]                        --gaps mt,lcWGS  gap before these columns
  --columns a,b,...       column subset/order [all]                         --rows input|alpha|total [input]
  --font Arial --font-size 8 --value-size 7 --weight bold|normal            --italic auto|all|none [auto]
  --col-italic yes|no [yes]   --abbreviate-genus yes|no [no]   --side-bar yes|no [yes]   --colorbar yes|no [yes]
  --cell 0.42,0.22 (inch w,h)  --highlight ROW (box + connector to next panel)  --highlight-color #d9541e
  --formats pdf,png[,svg]  --dpi 300  --out prefix
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib import colors as mcolors             # noqa: E402
from matplotlib.transforms import offset_copy        # noqa: E402
from matplotlib.lines import Line2D                  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxname import abbreviate, segments            # noqa: E402

matplotlib.rcParams["pdf.fonttype"] = 42            # editable text in Illustrator
matplotlib.rcParams["svg.fonttype"] = "none"


def ensure_font(name):
    """Register a system font matplotlib has not scanned (e.g. Windows fonts under WSL) via fc-list; else fall back."""
    import logging
    import subprocess
    from matplotlib import font_manager as fm
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    try:
        fm.findfont(fm.FontProperties(family=name), fallback_to_default=False)
        return name
    except ValueError:
        pass
    try:
        out = subprocess.run(["fc-list", f":family={name}", "file"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        out = ""
    for f in (x.strip().rstrip(":") for x in out.splitlines() if x.strip()):
        try:
            fm.fontManager.addfont(f)
        except Exception:
            pass
    try:
        fm.findfont(fm.FontProperties(family=name), fallback_to_default=False)
        return name
    except ValueError:
        print(f"warning: font {name!r} not found; using DejaVu Sans")
        return "DejaVu Sans"


def per(lst, i, default):
    return (lst[i] if i < len(lst) else lst[-1]) if lst else default


def yes(x):
    return str(x).lower() in ("yes", "y", "true", "1", "on")


def get_cmap(spec):
    if "," in spec:
        return mcolors.LinearSegmentedColormap.from_list("user", spec.split(","))
    return plt.get_cmap(spec)


def fmt(v):
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


class Typesetter:
    """Draw mixed italic/upright labels right-aligned at a data point (baselines aligned)."""

    def __init__(self, fig, font, size, weight, mode):
        self.fig, self.font, self.size, self.weight, self.mode = fig, font, size, weight, mode
        self.r = fig.canvas.get_renderer()
        self._cache = {}

    def width(self, s, italic):
        k = (s, italic)
        if k not in self._cache:
            t = self.fig.text(0, 0, s, fontsize=self.size, family=self.font, weight=self.weight,
                              style="italic" if italic else "normal")
            self._cache[k] = t.get_window_extent(self.r).width * 72 / self.fig.dpi
            t.remove()
        return self._cache[k]

    def space(self):
        return self.width("a a", False) - self.width("aa", False)

    def runs(self, label):
        out = []
        for txt, it in segments(label, self.mode):
            words = txt.split(" ")
            for j, w in enumerate(words):
                if w:
                    out.append((w, it))
                if j < len(words) - 1:
                    out.append((" ", it))
        return out

    def measure(self, label):
        return sum(self.space() if w == " " else self.width(w, it) for w, it in self.runs(label))

    def draw(self, ax, x, y, label, rot=False):
        runs = self.runs(label)
        if rot:                                     # vertical panel label: single style
            it = all(i for w, i in runs if w != " ")
            ax.text(x, y, label, rotation=90, ha="center", va="center", fontsize=self.size + 3, family=self.font,
                    weight="bold", style="italic" if it else "normal", transform=ax.transAxes, clip_on=False)
            return
        off = -self.measure(label)
        for w, it in runs:
            wd = self.space() if w == " " else self.width(w, it)
            if w != " ":
                ax.text(x, y, w, ha="left", va="center_baseline", fontsize=self.size, family=self.font,
                        weight=self.weight, style="italic" if it else "normal", clip_on=False,
                        transform=offset_copy(ax.transData, fig=self.fig, x=off, units="points"))
            off += wd


def main(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("taxon", nargs="?", default="")
    p.add_argument("--matrix", action="append", required=True)
    p.add_argument("--label", action="append", default=[])
    p.add_argument("--cmap", action="append", default=[])
    p.add_argument("--vmax", action="append", default=[])
    p.add_argument("--log", action="append", default=[])
    p.add_argument("--abbreviate-genus", action="append", default=[])
    p.add_argument("--highlight", action="append", default=[], help="row of panel i linked to panel i+1")
    p.add_argument("--highlight-color", default="#d9541e")
    p.add_argument("--values", default="yes")
    p.add_argument("--zero", choices=["cross", "blank", "grey", "zero"], default="cross")
    p.add_argument("--gaps", default="mt,lcWGS")
    p.add_argument("--columns")
    p.add_argument("--rows", choices=["input", "alpha", "total"], default="input")
    p.add_argument("--font", default="Arial")
    p.add_argument("--font-size", type=float, default=8)
    p.add_argument("--value-size", type=float)
    p.add_argument("--weight", default="bold")
    p.add_argument("--italic", choices=["auto", "all", "none"], default="auto")
    p.add_argument("--col-italic", default="yes")
    p.add_argument("--side-bar", default="yes")
    p.add_argument("--colorbar", default="yes")
    p.add_argument("--cell", default="0.42,0.22")
    p.add_argument("--formats", default="pdf,png")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--out", default="heatmap")
    a = p.parse_args(argv)
    cw, ch = (float(x) for x in a.cell.split(","))
    a.font = ensure_font(a.font)
    vsize = a.value_size or a.font_size - 1
    gaps = set(filter(None, a.gaps.split(",")))

    panels = []
    for i, f in enumerate(a.matrix):
        m = pd.read_csv(f, sep="\t", index_col=0)
        m.index = m.index.astype(str)
        if a.columns:
            m = m.reindex(columns=a.columns.split(","), fill_value=0)
        m = m.fillna(0)
        if a.rows == "alpha":
            m = m.sort_index()
        elif a.rows == "total":
            m = m.loc[m.sum(1).sort_values(ascending=False).index]
        shown = [abbreviate(r) if yes(per(a.abbreviate_genus, i, "no")) else r for r in m.index]
        vm = per(a.vmax, i, "auto")
        vmax = float(m.values.max() or 1) if vm == "auto" else float(vm)
        panels.append(dict(m=m, shown=shown, label=per(a.label, i, ""), cmap=get_cmap(per(a.cmap, i, "viridis")),
                           vmax=vmax, log=yes(per(a.log, i, "no")), hl=a.highlight[i] if i < len(a.highlight) else ""))

    fig = plt.figure(figsize=(8, 8), dpi=a.dpi)
    ts = Typesetter(fig, a.font, a.font_size, a.weight, a.italic)
    lab_w = max(ts.measure(s) for pn in panels for s in pn["shown"]) / 72 + 0.12
    side = 0.45 if yes(a.side_bar) or any(pn["label"] for pn in panels) else 0.1
    cbar = 0.85 if yes(a.colorbar) else 0.1
    top, gap_v, bottom = 0.38, 0.55, 0.12
    xs_all = []
    for pn in panels:
        xs, x = [], 0.0
        for c in pn["m"].columns:
            x += 0.35 if c in gaps else 0
            xs.append(x)
            x += 1
        pn["xs"], pn["ncell"] = xs, x
        xs_all.append(x)
    grid_w = max(xs_all) * cw
    W = side + lab_w + grid_w + cbar
    H = sum(top + len(pn["m"]) * ch for pn in panels) + gap_v * (len(panels) - 1) + bottom
    fig.set_size_inches(W, H)
    ts = Typesetter(fig, a.font, a.font_size, a.weight, a.italic)      # renderer for the final size

    ytop = H
    for i, pn in enumerate(panels):
        m, n = pn["m"], len(pn["m"])
        ytop -= top
        ax = fig.add_axes([(side + lab_w) / W, (ytop - n * ch) / H, pn["ncell"] * cw / W, n * ch / H])
        pn["ax"], ytop = ax, ytop - n * ch - gap_v
        norm = (mcolors.LogNorm(1, max(pn["vmax"], 1.01)) if pn["log"] else mcolors.Normalize(1, max(pn["vmax"], 1.01)))
        for r in range(n):
            for j, c in enumerate(m.columns):
                v, x0 = float(m.iat[r, j]), pn["xs"][j]
                if v == 0 and a.zero != "zero":
                    fc = {"grey": "0.88"}.get(a.zero, "white")
                    ax.add_patch(plt.Rectangle((x0, r), 1, 1, fc=fc, ec="0.35", lw=0.5))
                    if a.zero == "cross":
                        ax.plot([x0, x0 + 1], [r, r + 1], c="0.35", lw=0.5)
                        ax.plot([x0, x0 + 1], [r + 1, r], c="0.35", lw=0.5)
                    continue
                col = pn["cmap"](norm(min(max(v, 1), pn["vmax"]))) if v > 0 else (1, 1, 1, 1)
                ax.add_patch(plt.Rectangle((x0, r), 1, 1, fc=col, ec="0.6", lw=0.5))
                if yes(a.values):
                    lum = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
                    ax.text(x0 + 0.5, r + 0.5, fmt(v), ha="center", va="center", fontsize=vsize, family=a.font,
                            color="black" if lum > 0.55 else "white")
        ax.set_xlim(0, pn["ncell"])
        ax.set_ylim(n, 0)
        ax.set_xticks([x + 0.5 for x in pn["xs"]])
        ax.set_xticklabels(m.columns, fontsize=a.font_size, family=a.font, weight=a.weight,
                           style="italic" if yes(a.col_italic) else "normal")
        ax.xaxis.tick_top()
        ax.set_yticks(np.arange(n) + 0.5)
        ax.set_yticklabels([""] * n)
        ax.tick_params(length=2, pad=1)
        for s in ax.spines.values():
            s.set_visible(False)
        for r, s in enumerate(pn["shown"]):
            ts.draw(ax, -0.12, r + 0.5, s)
        bar_x = -(lab_w + 0.08) / (pn["ncell"] * cw)
        if yes(a.side_bar):
            ax.add_line(Line2D([bar_x, bar_x], [0, 1], transform=ax.transAxes, color="0.15", lw=7,
                               solid_capstyle="butt", clip_on=False))
        if pn["label"]:
            ts.draw(ax, bar_x - 0.18 / (pn["ncell"] * cw), 0.5, pn["label"], rot=True)
        if yes(a.colorbar):
            cax = fig.add_axes([(side + lab_w + grid_w + 0.18) / W, ax.get_position().y0,
                                0.14 / W, ax.get_position().height])
            sm = plt.cm.ScalarMappable(norm=norm, cmap=pn["cmap"])
            cb = fig.colorbar(sm, cax=cax)
            cb.ax.tick_params(labelsize=a.font_size - 1)
            if not pn["log"]:
                from matplotlib.ticker import MaxNLocator
                cb.locator = MaxNLocator(nbins=5, integer=True)
                cb.update_ticks()
            for t in cb.ax.get_yticklabels():
                t.set_family(a.font)
            if float(m.values.max()) > pn["vmax"]:
                cb.ax.text(0.5, 1.01, f">{fmt(pn['vmax'])}", transform=cb.ax.transAxes, ha="center", va="bottom",
                           fontsize=a.font_size - 1, family=a.font)

    for i, pn in enumerate(panels):                       # highlight + connector to next panel
        if not pn["hl"]:
            continue
        if pn["hl"] not in list(pn["m"].index):
            print(f"warning: highlight row {pn['hl']!r} not in panel {i + 1}")
            continue
        ax, r = pn["ax"], list(pn["m"].index).index(pn["hl"])
        x_left = -(lab_w - 0.02) / cw
        box = plt.Rectangle((x_left, r - 0.06), pn["ncell"] - x_left + 0.05, 1.12, fill=False,
                            ec=a.highlight_color, lw=1.3, clip_on=False)
        ax.add_patch(box)
        if i + 1 < len(panels):
            nx = panels[i + 1]["ax"]
            inv = fig.transFigure.inverted()
            p1 = inv.transform(ax.transData.transform((x_left, r + 1.06)))
            p2 = inv.transform(ax.transData.transform((pn["ncell"] + 0.05, r + 1.06)))
            q1 = inv.transform(nx.transData.transform((x_left, -0.15)))
            q2 = inv.transform(nx.transData.transform((panels[i + 1]["ncell"] + 0.05, -0.15)))
            for s, e in ((p1, q1), (p2, q2)):
                fig.add_artist(Line2D([s[0], e[0]], [s[1], e[1]], transform=fig.transFigure,
                                      color=a.highlight_color, lw=1.1))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for ext in a.formats.split(","):
        fig.savefig(f"{out}.{ext}", dpi=a.dpi)
    print(f"02_plot: {len(panels)} panel(s) -> " + ", ".join(f"{out}.{e}" for e in a.formats.split(",")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
