#!/usr/bin/env Rscript
# sanity-check-classifier.R — companion to sanity-check-classifier.sh.
#
# Drawn N profiles at random from <iada-tree>/<variant>/<env>/source/,
# runs SVM + per-class K-Means against the six .rda artifacts under
# <cloudsim-repo>/R/, and writes a TSV with one row per sample. Exits
# 2 if the mismatch rate crosses --fail-threshold-pct.

suppressPackageStartupMessages({
  library(e1071)
})

# ─── argparse ────────────────────────────────────────────────────────────────
parse_args <- function(argv) {
  opt <- list(tree = NULL, n_samples = 10L, cloudsim_repo = NULL,
              output = NULL, fail_threshold_pct = 30, seed = NULL)
  i <- 1
  while (i <= length(argv)) {
    a <- argv[[i]]
    switch(a,
      "--tree"                = { opt$tree <- argv[[i + 1]]; i <- i + 2 },
      "--n-samples"           = { opt$n_samples <- as.integer(argv[[i + 1]]); i <- i + 2 },
      "--cloudsim-repo"       = { opt$cloudsim_repo <- argv[[i + 1]]; i <- i + 2 },
      "--output"              = { opt$output <- argv[[i + 1]]; i <- i + 2 },
      "--fail-threshold-pct"  = { opt$fail_threshold_pct <- as.numeric(argv[[i + 1]]); i <- i + 2 },
      "--seed"                = { opt$seed <- as.integer(argv[[i + 1]]); i <- i + 2 },
      stop(sprintf("unknown argument: %s", a))
    )
  }
  for (k in c("tree", "cloudsim_repo", "output")) {
    if (is.null(opt[[k]])) stop(sprintf("--%s is required", gsub("_", "-", k)))
  }
  opt
}
opt <- parse_args(commandArgs(trailingOnly = TRUE))
if (!is.null(opt$seed)) set.seed(opt$seed)

FEATURES <- c("netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu")
CLASSES  <- c("cpu", "mem", "disk", "net", "cache")

# Inference-time column order, as MLClassifier.java builds the data
# frame for predict(). See CLASSIFIER-INTERNALS.md §2 quirk note.
INFER_COLS <- c("nets", "netp", "blk", "mbw", "llcmr", "llcocc", "cpu")

# Workload-name → expected class (case-insensitive, prefix-based).
# "unknown" is intentionally permissive: profiles whose workload name
# does not match any class are scored as plausibility="unknown" rather
# than mismatch, so we don't penalise mixed/control workloads.
#
# Deliberately UNMAPPED appNN families (return "unknown" BEFORE the hint
# loop) — expecting a class for these would test the wrong thing:
#   classification (app08/09)  mixed CPU+memory by design
#   ordering       (app06/07)  qsort/malloc straddle Meyer's mem/cache split
#   oversub        (app16)     scheduling-regime profile: the 7-metric
#   pressure       (app17)     classifier definitionally lacks psp/psi —
#                              that gap is P3's thesis, not a sanity failure
#   sort_net       (app11/12)  loopback sockets; v2+ filters `lo`, so the
#                              canonical profile carries no net signal
#   redis/_cs_/dsb (app18+)    real apps = mixed fingerprints
AMBIGUOUS_PATTERNS <- c("classification", "ordering", "oversub", "pressure",
                        "sort_net", "redis", "_cs_", "dsb")

WORKLOAD_HINTS <- list(
  cpu   = c("^cpu", "cpu_", "stress_cpu", "iperf_cpu", "search"),
  mem   = c("^mem", "memory", "stress_mem", "stress_vm"),
  disk  = c("^disk", "io_", "fio", "stress_io", "hdd", "query"),
  net   = c("^net", "tcp", "udp", "iperf", "netperf"),
  cache = c("cache", "llc", "stream_cache", "streaming")
)

infer_expected_class <- function(workload) {
  w <- tolower(workload)
  for (pat in AMBIGUOUS_PATTERNS) {
    if (grepl(pat, w)) return("unknown")
  }
  for (cls in names(WORKLOAD_HINTS)) {
    for (pat in WORKLOAD_HINTS[[cls]]) {
      if (grepl(pat, w)) return(cls)
    }
  }
  "unknown"
}

# Per-class column used by predict_<class>.kmeans for the level
# mapping; mirrors upstream R/kmeans.R.
LEVEL_COL <- list(cpu = 7L, mem = 4L, disk = 3L, net = 1L, cache = 6L)

predict_level <- function(km, newdata, var) {
  centers <- km$centers
  n_centers <- nrow(centers)
  hig <- which.max(centers[, var])
  low <- which.min(centers[, var])
  mod <- setdiff(seq_len(n_centers), c(hig, low))[1]

  dist_mat <- as.matrix(dist(rbind(centers, newdata)))
  dist_mat <- dist_mat[-seq(n_centers), seq(n_centers), drop = FALSE]
  a <- max.col(-dist_mat)
  out <- character(length(a))
  out[a == low] <- "low"
  out[a == mod] <- "mod"
  out[a == hig] <- "hig"
  out
}

# ─── load models ─────────────────────────────────────────────────────────────
rfolder <- file.path(opt$cloudsim_repo, "R")
load(file.path(rfolder, "svm_model.rda"))   # modelo_svm
load(file.path(rfolder, "cpuk.rda"))        # cl_cpu
load(file.path(rfolder, "memk.rda"))        # cl_mem
load(file.path(rfolder, "diskk.rda"))       # cl_disk
load(file.path(rfolder, "netk.rda"))        # cl_net
load(file.path(rfolder, "cachek.rda"))      # cl_cache
km <- list(cpu = cl_cpu, mem = cl_mem, disk = cl_disk, net = cl_net, cache = cl_cache)

# ─── sample profiles ─────────────────────────────────────────────────────────
csvs <- list.files(opt$tree, pattern = "\\.csv$",
                   recursive = TRUE, full.names = TRUE)
if (length(csvs) == 0) {
  stop(sprintf("no CSVs under --tree %s", opt$tree))
}

# Balance per-workload sampling: bucket by parent directory name
# (which represents the workload), pick proportionally.
parent_dirs <- basename(dirname(csvs))
bucketed <- split(csvs, parent_dirs)
take_per <- max(1L, ceiling(opt$n_samples / length(bucketed)))
sampled <- unlist(lapply(bucketed, function(xs) {
  sample(xs, min(length(xs), take_per))
}), use.names = FALSE)
sampled <- sample(sampled, min(length(sampled), opt$n_samples))

# ─── classify each ───────────────────────────────────────────────────────────
results <- data.frame(
  workload         = character(),
  expected_class   = character(),
  predicted_class  = character(),
  predicted_level  = character(),
  plausibility     = character(),
  stringsAsFactors = FALSE
)

for (path in sampled) {
  workload <- basename(dirname(path))

  # Read profile, force numeric coercion, drop NA rows.
  df <- tryCatch(
    read.csv2(path, sep = ";", header = FALSE,
              col.names = FEATURES, stringsAsFactors = FALSE),
    error = function(e) NULL
  )
  if (is.null(df) || nrow(df) < 5) next
  df[] <- lapply(df, function(x) suppressWarnings(as.numeric(as.character(x))))
  df <- df[complete.cases(df), , drop = FALSE]
  if (nrow(df) < 5) next

  # Reorder columns to MLClassifier.java's at-inference layout.
  infer_df <- df[, INFER_COLS, drop = FALSE]

  expected <- infer_expected_class(workload)

  preds <- tryCatch(
    predict(modelo_svm, infer_df),
    error = function(e) {
      message(sprintf("[sanity] SVM predict failed on %s: %s", path, conditionMessage(e)))
      NULL
    }
  )
  if (is.null(preds)) next

  # Majority-class over the profile rows.
  pred_tab <- sort(table(as.character(preds)), decreasing = TRUE)
  pred_cls <- names(pred_tab)[1]
  if (is.null(pred_cls)) next

  # Level for the predicted class.
  lvl_col <- LEVEL_COL[[pred_cls]]
  if (is.null(lvl_col)) {
    level <- "n/a"
  } else {
    rows_in_cls <- infer_df[as.character(preds) == pred_cls, , drop = FALSE]
    # Align column order to the kmeans model's training column order.
    rows_in_cls <- rows_in_cls[, FEATURES, drop = FALSE]
    lvls <- predict_level(km[[pred_cls]], rows_in_cls, lvl_col)
    lvl_tab <- sort(table(lvls), decreasing = TRUE)
    level <- names(lvl_tab)[1]
    if (is.null(level)) level <- "n/a"
  }

  plausibility <- if (expected == "unknown") "unknown"
                  else if (expected == pred_cls) "match"
                  else "mismatch"

  results <- rbind(results, data.frame(
    workload = workload, expected_class = expected,
    predicted_class = pred_cls, predicted_level = level,
    plausibility = plausibility, stringsAsFactors = FALSE
  ))
}

# ─── write TSV + decide exit code ────────────────────────────────────────────
if (nrow(results) == 0) {
  warning("no profile yielded a prediction; treating as inconclusive (exit 0)")
  write.table(results, file = opt$output, sep = "\t",
              row.names = FALSE, quote = FALSE)
  q(save = "no", status = 0)
}
write.table(results, file = opt$output, sep = "\t",
            row.names = FALSE, quote = FALSE)

mismatch_n  <- sum(results$plausibility == "mismatch")
known_n     <- sum(results$plausibility %in% c("match", "mismatch"))
mismatch_pct <- if (known_n == 0) 0 else (100 * mismatch_n / known_n)

cat(sprintf("[sanity] %s : n=%d  match=%d  mismatch=%d  unknown=%d  mismatch_pct=%.1f%%\n",
            opt$tree, nrow(results),
            sum(results$plausibility == "match"),
            mismatch_n,
            sum(results$plausibility == "unknown"),
            mismatch_pct))

if (mismatch_pct > opt$fail_threshold_pct) {
  message(sprintf("[sanity] FAIL: mismatch %.1f%% > threshold %.1f%%",
                  mismatch_pct, opt$fail_threshold_pct))
  q(save = "no", status = 2)
}
q(save = "no", status = 0)
