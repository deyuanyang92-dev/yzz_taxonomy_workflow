#!/usr/bin/env Rscript
# molheat.R — count-matrix TSV(s) from 01_count.py -> heatmap (PDF/PNG/SVG). R twin of 02_plot.py, same options.
# Packages: ggplot2, jsonlite (+ ragg for PNG if installed). Taxon names are typeset from name_style.json
# (shared with taxname.py): genus/epithets italic; sp./cf./aff./und., informal codes, authors, family names upright.
#
#   Rscript molheat.R --matrix Eunicidae_genus.tsv --matrix Marphysa_species.tsv \
#     --label Eunicidae --label Marphysa --cmap viridis --cmap magma --vmax 200 --vmax 20 \
#     --abbreviate-genus no --abbreviate-genus yes --highlight Marphysa --out Eunicidae_heatmap_R
#   Rscript molheat.R --print-labels "Marphysa sp. E HA-2019" "Eunicidae und."     # debug typesetting
#
# Options (defaults in brackets; per-panel options repeat once per --matrix, last value reused):
#   --cmap viridis|magma|inferno|plasma|cividis|mako|rocket|turbo|c1,c2,...  [viridis]   --vmax auto|N [auto]
#   --log yes|no [no]  --values yes|no [yes]  --zero cross|blank|grey|zero [cross]  --gaps mt,lcWGS
#   --columns a,b,...  --rows input|alpha|total [input]  --font Arial  --font-size 8  --value-size 7
#   --weight bold|normal [bold]  --italic auto|all|none [auto]  --col-italic yes|no [yes]
#   --abbreviate-genus yes|no [no]  --side-bar yes|no [yes]  --colorbar yes|no [yes]  --cell 0.42,0.22 (inch)
#   --highlight ROW  --highlight-color #d9541e  --formats pdf,png  --dpi 300  --out prefix

suppressPackageStartupMessages({ library(ggplot2); library(grid); library(jsonlite) })

script_dir <- function() {
  f <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))
  if (length(f)) dirname(normalizePath(f[1])) else getwd()
}
STYLE <- fromJSON(file.path(script_dir(), "name_style.json"))
UP <- tolower(STYLE$upright_tokens); REST <- tolower(STYLE$rest_upright_after)

# ---------- options ----------
parse_args <- function(args) {
  o <- list(); pos <- character(); i <- 1
  while (i <= length(args)) {
    a <- args[i]
    if (a == "--print-labels") { o$print_labels <- args[(i + 1):length(args)]; break }
    if (startsWith(a, "--")) {
      k <- gsub("-", "_", substring(a, 3)); o[[k]] <- c(o[[k]], args[i + 1]); i <- i + 2
    } else { pos <- c(pos, a); i <- i + 1 }
  }
  o
}
opt <- parse_args(commandArgs(TRUE))
g1 <- function(k, d) if (is.null(opt[[k]])) d else opt[[k]][1]
per <- function(k, i, d) { v <- opt[[k]]; if (is.null(v)) d else v[min(i, length(v))] }
yes <- function(x) tolower(x) %in% c("yes", "y", "true", "1", "on")

# ---------- taxon-name typography (same rules as taxname.py) ----------
is_higher <- function(w) {
  w <- gsub("[()\\[\\],]", "", w)
  w %in% STYLE$higher_taxa || (grepl("^[A-Z]", w) && any(endsWith(w, STYLE$higher_rank_suffixes)))
}
token_flags <- function(name) {
  toks <- strsplit(trimws(name), "\\s+")[[1]]
  if (!length(toks)) return(data.frame(t = character(), it = logical()))
  if (is_higher(toks[1])) return(data.frame(t = toks, it = FALSE))
  it <- logical(length(toks)); rest <- FALSE
  for (i in seq_along(toks)) {
    t <- toks[i]; low <- tolower(t)
    if (rest) { it[i] <- FALSE; next }
    if (i == 2 && grepl("^\\([A-Z][a-z]+\\)$", t)) { it[i] <- TRUE; next }
    if (i >= 2 && (grepl("^[A-Z]", t) || startsWith(t, "(")) && !(low %in% UP)) { rest <- TRUE; it[i] <- FALSE; next }
    up <- low %in% UP || any(vapply(STYLE$upright_regex, function(r) grepl(r, t, perl = TRUE), logical(1)))
    if (low %in% REST) rest <- TRUE
    it[i] <- !up
  }
  data.frame(t = toks, it = it)
}
segments_of <- function(name, mode = "auto") {
  name <- gsub("\\s+", " ", trimws(name))
  if (mode == "all") return(data.frame(t = name, it = TRUE))
  if (mode == "none") return(data.frame(t = name, it = FALSE))
  f <- token_flags(name); out <- data.frame(t = character(), it = logical())
  for (i in seq_len(nrow(f))) {
    n <- nrow(out)
    if (n && out$it[n] == f$it[i]) out$t[n] <- paste(out$t[n], f$t[i])
    else { if (n) out$t[n] <- paste0(out$t[n], " "); out <- rbind(out, f[i, ]) }
  }
  out
}
abbreviate_genus <- function(name) {
  toks <- strsplit(name, " ")[[1]]
  if (length(toks) < 2 || is_higher(toks[1]) || tolower(toks[2]) %in% c("sp.", "spp.", "sp", "spp")) return(name)
  if (grepl("^[A-Z][a-z]+$", toks[1])) paste0(substr(toks[1], 1, 1), ". ", paste(toks[-1], collapse = " ")) else name
}
plotmath <- function(name, mode, bold) {
  s <- segments_of(name, mode)
  q <- function(x) paste0("\"", gsub("\"", "\\\\\"", gsub("\\\\", "\\\\\\\\", x)), "\"")
  parts <- vapply(seq_len(nrow(s)), function(i) {
    f <- if (s$it[i]) (if (bold) "bolditalic" else "italic") else (if (bold) "bold" else "plain")
    sprintf("%s(%s)", f, q(s$t[i]))
  }, "")
  if (length(parts) == 1) parts else sprintf("paste(%s)", paste(parts, collapse = ", "))
}

if (!is.null(opt$print_labels)) {
  for (n in opt$print_labels) {
    s <- segments_of(n)
    cat(n, "=>", paste(sprintf("%s:'%s'", ifelse(s$it, "I", "R"), s$t), collapse = " | "), "\n")
  }
  quit(save = "no")
}

# ---------- settings ----------
mats <- opt$matrix; if (is.null(mats)) stop("--matrix required")
font <- g1("font", "Arial"); fs <- as.numeric(g1("font_size", 8)); vs <- as.numeric(g1("value_size", fs - 1))
bold <- g1("weight", "bold") == "bold"; imode <- g1("italic", "auto"); zero <- g1("zero", "cross")
gaps <- strsplit(g1("gaps", "mt,lcWGS"), ",")[[1]]
cell <- as.numeric(strsplit(g1("cell", "0.42,0.22"), ",")[[1]]); cw <- cell[1]; ch <- cell[2]
hl_col <- g1("highlight_color", "#d9541e"); out <- g1("out", "heatmap_R")
formats <- strsplit(g1("formats", "pdf,png"), ",")[[1]]; dpi <- as.numeric(g1("dpi", 300))
pt <- 72.27 / 25.4                                     # ggplot size units (mm) per pt

pal <- function(spec) {
  if (grepl(",", spec)) return(strsplit(spec, ",")[[1]])
  if (requireNamespace("viridisLite", quietly = TRUE) &&
      spec %in% c("viridis", "magma", "inferno", "plasma", "cividis", "mako", "rocket", "turbo"))
    return(viridisLite::viridis(256, option = spec))
  hcl.colors(256, spec)
}
fmtv <- function(v) ifelse(v == round(v), format(round(v), trim = TRUE), sprintf("%.1f", v))

# ---------- one panel ----------
build <- function(i) {
  m <- read.delim(mats[i], check.names = FALSE, stringsAsFactors = FALSE)
  rn <- as.character(m[[1]]); m <- as.matrix(m[, -1, drop = FALSE]); rownames(m) <- rn; m[is.na(m)] <- 0
  if (!is.null(opt$columns)) {
    cols <- strsplit(opt$columns[1], ",")[[1]]
    mm <- matrix(0, nrow(m), length(cols), dimnames = list(rn, cols))
    common <- intersect(cols, colnames(m)); mm[, common] <- m[, common]; m <- mm
  }
  ro <- g1("rows", "input")
  if (ro == "alpha") m <- m[order(rownames(m)), , drop = FALSE]
  if (ro == "total") m <- m[order(-rowSums(m)), , drop = FALSE]
  shown <- if (yes(per("abbreviate_genus", i, "no"))) vapply(rownames(m), abbreviate_genus, "") else rownames(m)
  xs <- numeric(ncol(m)); x <- 0
  for (j in seq_len(ncol(m))) { if (colnames(m)[j] %in% gaps) x <- x + 0.35; xs[j] <- x; x <- x + 1 }
  vm <- per("vmax", i, "auto"); vmax <- if (vm == "auto") max(m, 1) else as.numeric(vm)
  lg <- yes(per("log", i, "no"))
  d <- expand.grid(r = seq_len(nrow(m)), j = seq_len(ncol(m)))
  d$v <- m[cbind(d$r, d$j)]; d$x0 <- xs[d$j]; d$y0 <- d$r - 1
  d$vc <- pmin(pmax(d$v, 1), vmax)
  nz <- d[d$v > 0 | zero == "zero", ]; z <- d[d$v == 0 & zero != "zero", ]
  cols <- pal(per("cmap", i, "viridis"))
  p <- ggplot() +
    geom_rect(data = nz, aes(xmin = x0, xmax = x0 + 1, ymin = y0, ymax = y0 + 1, fill = vc), colour = "grey60", linewidth = 0.25)
  if (nrow(z)) {
    p <- p + geom_rect(data = z, aes(xmin = x0, xmax = x0 + 1, ymin = y0, ymax = y0 + 1),
                       fill = if (zero == "grey") "grey88" else "white", colour = "grey35", linewidth = 0.25)
    if (zero == "cross")
      p <- p + geom_segment(data = z, aes(x = x0, xend = x0 + 1, y = y0, yend = y0 + 1), colour = "grey35", linewidth = 0.25) +
        geom_segment(data = z, aes(x = x0, xend = x0 + 1, y = y0 + 1, yend = y0), colour = "grey35", linewidth = 0.25)
  }
  if (yes(g1("values", "yes")) && nrow(nz)) {
    rgbv <- col2rgb(colorRampPalette(cols)(256)[pmax(1, round(255 * (if (lg) log(nz$vc) / log(max(vmax, 1.01)) else (nz$vc - 1) / max(vmax - 1, 0.01))) + 1)])
    nz$tc <- ifelse(0.299 * rgbv[1, ] + 0.587 * rgbv[2, ] + 0.114 * rgbv[3, ] > 140, "black", "white")
    p <- p + geom_text(data = nz, aes(x = x0 + 0.5, y = y0 + 0.5, label = fmtv(v), colour = I(tc)), size = vs / pt, family = font)
  }
  brk <- pretty(c(1, vmax), n = 5); brk <- brk[brk >= 1 & brk <= vmax & brk == round(brk)]
  lab <- as.character(brk)
  if (max(m) > vmax) { keep <- brk < vmax * 0.93; brk <- c(brk[keep], vmax); lab <- c(lab[keep], paste0(">", fmtv(vmax))) }
  p <- p + scale_fill_gradientn(colours = cols, limits = c(1, max(vmax, 1.01)), breaks = brk, labels = lab,
                                trans = if (lg) "log10" else "identity", oob = scales::squish,
                                guide = if (yes(g1("colorbar", "yes"))) guide_colourbar(barwidth = unit(0.14, "in"),
                                  barheight = unit(nrow(m) * ch, "in"), title = NULL, ticks.colour = "black") else "none") +
    scale_x_continuous(breaks = xs + 0.5, labels = colnames(m), position = "top", expand = c(0, 0)) +
    scale_y_reverse(breaks = seq_len(nrow(m)) - 0.5, expand = c(0, 0),
                    labels = parse(text = vapply(shown, plotmath, "", mode = imode, bold = bold))) +
    coord_cartesian(clip = "off") +
    theme_void(base_family = font, base_size = fs) +
    theme(axis.text.x.top = element_text(size = fs, face = if (yes(g1("col_italic", "yes"))) (if (bold) "bold.italic" else "italic") else (if (bold) "bold" else "plain"),
                                         margin = margin(b = 2)),
          axis.text.y = element_text(size = fs, hjust = 1, margin = margin(r = 3)),
          axis.ticks = element_line(linewidth = 0.3), axis.ticks.length = unit(2, "pt"),
          legend.text = element_text(size = fs - 1), legend.margin = margin(l = 6),
          plot.margin = margin(4, 4, 4, 4))
  list(p = p, m = m, xs = xs, ncell = x, label = per("label", i, ""), hl = if (length(opt$highlight) >= i) opt$highlight[i] else "")
}

cairo_pdf(tempfile(fileext = ".pdf"), family = font)    # device for string-width conversion (cairo knows system fonts)
panels <- lapply(seq_along(mats), build)
grobs <- lapply(panels, function(pn) ggplotGrob(pn$p))
# fix the panel cell size in inches and align left edges across panels
for (k in seq_along(grobs)) {
  g <- grobs[[k]]; pr <- g$layout$t[g$layout$name == "panel"]; pc <- g$layout$l[g$layout$name == "panel"]
  g$heights[pr] <- unit(nrow(panels[[k]]$m) * ch, "in"); g$widths[pc] <- unit(panels[[k]]$ncell * cw, "in")
  grobs[[k]] <- g
}
inch_w <- function(u) convertWidth(u, "in", valueOnly = TRUE)
inch_h <- function(u) convertHeight(u, "in", valueOnly = TRUE)
lab_w <- max(vapply(grobs, function(g) { pc <- g$layout$l[g$layout$name == "panel"]; sum(inch_w(g$widths[1:(pc - 1)])) }, 0))
side <- if (yes(g1("side_bar", "yes")) || any(nzchar(vapply(panels, `[[`, "", "label")))) 0.6 else 0
heights <- vapply(grobs, function(g) sum(inch_h(g$heights)), 0)
widths <- vapply(grobs, function(g) sum(inch_w(g$widths)), 0)
lefts <- vapply(grobs, function(g) { pc <- g$layout$l[g$layout$name == "panel"]; sum(inch_w(g$widths[1:(pc - 1)])) }, 0)
gap_v <- 0.35
W <- side + max(widths + (lab_w - lefts)); H <- sum(heights) + gap_v * (length(grobs) - 1)
invisible(dev.off())

draw <- function() {
  grid.newpage()
  y <- H; geo <- list()
  for (k in seq_along(grobs)) {
    g <- grobs[[k]]; pr <- g$layout$t[g$layout$name == "panel"]
    x0 <- side + (lab_w - lefts[k])
    pushViewport(viewport(x = unit(x0, "in"), y = unit(y, "in"), width = unit(widths[k], "in"),
                          height = unit(heights[k], "in"), just = c("left", "top")))
    grid.draw(g); popViewport()
    above <- sum(inch_h(g$heights[1:(pr - 1)])); ph <- nrow(panels[[k]]$m) * ch
    geo[[k]] <- list(top = y - above, bottom = y - above - ph, left = side + lab_w, right = side + lab_w + panels[[k]]$ncell * cw)
    bx <- side - 0.22
    if (yes(g1("side_bar", "yes")))
      grid.rect(x = unit(bx + 0.05, "in"), y = unit(geo[[k]]$bottom, "in"), width = unit(0.1, "in"), height = unit(ph, "in"),
                just = c("left", "bottom"), gp = gpar(fill = "grey15", col = NA))
    if (nzchar(panels[[k]]$label)) {
      s <- segments_of(panels[[k]]$label); itl <- all(s$it)
      grid.text(panels[[k]]$label, x = unit(bx - 0.12, "in"), y = unit((geo[[k]]$top + geo[[k]]$bottom) / 2, "in"), rot = 90,
                gp = gpar(fontfamily = font, fontsize = fs + 3, fontface = if (itl) "bold.italic" else "bold"))
    }
    y <- y - heights[k] - gap_v
  }
  for (k in seq_along(panels)) {                         # highlight box + connector
    hl <- panels[[k]]$hl
    if (!nzchar(hl)) next
    r <- match(hl, rownames(panels[[k]]$m))
    if (is.na(r)) { message("warning: highlight row ", hl, " not in panel ", k); next }
    gk <- geo[[k]]; yt <- gk$top - (r - 1) * ch + 0.012; yb <- gk$top - r * ch - 0.012
    xl <- side + 0.02; xr <- gk$right + 0.02
    grid.rect(x = unit(xl, "in"), y = unit(yb, "in"), width = unit(xr - xl, "in"), height = unit(yt - yb, "in"),
              just = c("left", "bottom"), gp = gpar(fill = NA, col = hl_col, lwd = 1.3))
    if (k < length(panels)) {
      gn <- geo[[k + 1]]
      grid.lines(unit(c(xl, xl), "in"), unit(c(yb, gn$top + 0.04), "in"), gp = gpar(col = hl_col, lwd = 1.1))
      grid.lines(unit(c(xr, gn$right + 0.02), "in"), unit(c(yb, gn$top + 0.04), "in"), gp = gpar(col = hl_col, lwd = 1.1))
    }
  }
}

dir.create(dirname(out), showWarnings = FALSE, recursive = TRUE)
for (f in formats) {
  fn <- paste0(out, ".", f)
  if (f == "pdf") cairo_pdf(fn, width = W, height = H, family = font)
  else if (f == "png") { if (requireNamespace("ragg", quietly = TRUE)) ragg::agg_png(fn, width = W, height = H, units = "in", res = dpi)
                         else png(fn, width = W, height = H, units = "in", res = dpi, type = "cairo") }
  else if (f == "svg") svg(fn, width = W, height = H, family = font)
  else { message("skip format ", f); next }
  draw(); invisible(dev.off())
}
cat("molheat.R:", length(panels), "panel(s) ->", paste0(out, ".", formats, collapse = ", "), "\n")
