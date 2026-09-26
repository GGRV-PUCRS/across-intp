# s6-refclass.R -- offline replication of MLClassifier.getMLClass(interf, 0, len)
# (the exact call IntContainerDataCenter.oracleRescore makes) for each reference
# classifier (T1, A, B), used by S6 to re-score the S1-saved final placements
# under every reference so the three matrix columns share placements.
#
# The classification inputs do NOT depend on which tier produced a placement:
# oracleRescore classifies cloudlet k's trace from the REFERENCE's own tree
# (oracleTreeDir) with the reference's model. So one cost per (reference,
# cloudlet) suffices for the whole 3x3 matrix; only the placement differs.
#
# This script mirrors MLClassifier.getMLClass's R eval sequence literally
# (same sourcing order, same zero-placeholder first row in `teste`, same
# svm_classifier_level(teste, 1, nrow(teste)) call) so the levels it returns
# are the levels the simulator would produce. Validated against the S3
# campaign's CLS log lines (narrow windows) before use (DECISIONS S6).
#
#   Rscript s6-refclass.R <rda-root> <trees-root> <out.tsv> [--window <start> <finish>]
#
# <rda-root>   holds <tier>/{input_dataset.R,misc.R,cpd.R,kmeans.R,svm.R,*.rda}
# <trees-root> holds tree-<tier>-vm-guest/<VARIANT>/<ENV>/source/<app>/<pat>.csv
# Output: one row per (ref, cloudlet): ref, cloudlet, workload, pattern, cost,
# and one column per resource level (cpu/mem/disk/net/cache[/regime]).
# --window replicates getMLClass(interf, start, finish) instead of the full
# window (validation mode; finish is EXCLUSIVE, as in the Java loop).

suppressMessages({ library(e1071); library(dplyr); library(stringr) })

# Degradation.java fork table (PAPER_TABLE=off, the committed default; every
# S16 run uses it -- no run set -Diada.degTable=paper).
DEG <- list(
  cpu    = c(abs = 1.00, low = 1.05, mod = 1.17, hig = 1.38),
  mem    = c(abs = 1.00, low = 1.10, mod = 1.67, hig = 1.79),
  disk   = c(abs = 1.00, low = 1.21, mod = 1.92, hig = 2.31),
  cache  = c(abs = 1.00, low = 1.12, mod = 1.24, hig = 1.32),
  net    = c(abs = 1.00, low = 1.13, mod = 1.43, hig = 1.62),
  regime = c(abs = 1.00, low = 1.20, mod = 1.55, hig = 1.95)
)

args <- commandArgs(trailingOnly = TRUE)
rda_root   <- args[1]
trees_root <- args[2]
out_path   <- args[3]
win <- NULL
if ("--window" %in% args) {
  i <- which(args == "--window")
  win <- c(as.integer(args[i + 1]), as.integer(args[i + 2])) # [start, finish)
}

VARIANT <- Sys.getenv("S6_VARIANT", unset = "v3.3")
ENV     <- Sys.getenv("S6_ENV", unset = "vm-guest")

# listSortedTraces() in IntContainerDataCenter: sorted subdirs, sorted files.
list_sorted_traces <- function(dir) {
  out <- c()
  subs <- sort(list.dirs(dir, full.names = FALSE, recursive = FALSE))
  for (s in subs) {
    files <- sort(list.files(file.path(dir, s), full.names = FALSE))
    for (f in files) out <- c(out, file.path(dir, s, f))
  }
  out
}

cloudlet_cost <- function(levels) {
  # MLCResult.getCloudletCost(): product over the classifier's own resource
  # rows (regime only present for the 6-class tier B model), floored at 1.
  cost <- 1.0
  for (res in names(levels)) {
    if (!is.na(levels[res])) cost <- cost * DEG[[res]][levels[res]]
  }
  max(cost, 1.0)
}

results <- list()
for (tier in c("T1", "A", "B")) {
  project_folder_inside <- paste0(rda_root, "/", tier, "/")
  training_dataset_folder <- paste0(project_folder_inside, "forced/")
  firstTime <- 1
  firstTimeK <- 1

  source(paste0(project_folder_inside, "input_dataset.R"))
  total <- input_dataset(training_dataset_folder)
  source(paste0(project_folder_inside, "misc.R"))
  source(paste0(project_folder_inside, "cpd.R"))
  source(paste0(project_folder_inside, "kmeans.R"))
  source(paste0(project_folder_inside, "svm.R"))

  feat_cols <- setdiff(names(total), "category")

  tree_dir <- file.path(trees_root, paste0("tree-", tier, "-vm-guest"),
                         VARIANT, ENV, "source")
  traces <- list_sorted_traces(tree_dir)
  stopifnot(length(traces) == 28)

  for (k in seq_along(traces)) {
    path <- traces[k]
    # Interference.importCsvInt: split on ";", integer fields, first width cols
    # are read by getMLClass via getIntByLine(i)[j], j < width.
    con <- file(path, open = "r")
    lines <- readLines(con, warn = FALSE)
    close(con)
    mat <- do.call(rbind, lapply(lines, function(l) {
      as.integer(strsplit(l, ";", fixed = TRUE)[[1]][seq_len(length(feat_cols))])
    }))
    if (!is.null(win)) {
      # Java loop: for (i = start; i < finish; i++) -> 0-based [start, finish)
      mat <- mat[(win[1] + 1):win[2], , drop = FALSE]
    }

    # MLClassifier.getMLClass: zero placeholder row, then rbind per integer row
    # (rbind coerces the frame to double, exactly as the Java-side eval path).
    teste <- setNames(as.data.frame(matrix(0, ncol = length(feat_cols))), feat_cols)
    for (r in seq_len(nrow(mat))) {
      aux <- as.data.frame(as.list(mat[r, ]))
      names(aux) <- feat_cols
      teste <- rbind(teste, aux)
    }

    res <- svm_classifier_level(teste, 1, nrow(teste))
    lv <- res$per
    names(lv) <- res$resource

    cost <- cloudlet_cost(lv)
    workload <- basename(dirname(path))
    pattern <- sub("\\.csv$", "", basename(path))
    row <- list(ref = tier, cloudlet = k, workload = workload, pattern = pattern,
                cost = cost)
    for (res_name in c("cpu", "mem", "disk", "net", "cache", "regime")) {
      row[[res_name]] <- ifelse(res_name %in% names(lv), lv[[res_name]], NA)
    }
    results[[length(results) + 1]] <- row
  }
  cat("reference", tier, "done:", length(traces), "traces\n")
}

df <- bind_rows(lapply(results, as.data.frame, stringsAsFactors = FALSE))
write.table(df, out_path, sep = "\t", quote = FALSE, row.names = FALSE)
cat("wrote", out_path, "\n")
