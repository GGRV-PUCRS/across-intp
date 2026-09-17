#!/usr/bin/env Rscript
# eval-tiers.R — F13: compare the 3 IADA classifier tiers per deployment env.
#
# IADA is retrained per domain (its own M2 guard mandates this; absolute proxy
# values are not cross-env comparable — e.g. membw_est is ~10x higher in the VM
# than the host for the same stressor). So the fair test is WITHIN-ENV k-fold CV:
# for each env (host = bare+container pooled, and vm-guest) and each tier, can the
# metric set separate the resource classes?
#
#   T1  canonical-7    : netp,nets,blk,mbw,llcmr,llcocc,cpu
#   A   proxy-swap     : membw_est in the mbw slot (so mem has a signal in the VM,
#                        where mbw/llcocc arrive as '--')
#   B   full-15+regime : all 15 metrics + a scheduling-regime class
#
# Same SVM as retrain.R (C-classification, nu=.1, scale, polynomial). Reports per
# (tier, env): CV accuracy, macro-F1, per-class recall; writes tier-eval.tsv.
#
#   Rscript eval-tiers.R <trainsets-root> [out.tsv] [k] [seed] [group]
#
# `group` (5th arg, 0/1, default 0): fold assignment strategy.
#   0 = flat shuffle (sample(rep(1:k, length.out=nrow(d))) over individual
#       rows) -- the ORIGINAL method, kept for direct before/after contrast.
#       Rows are 1-second samples within a rep's portable.tsv; adjacent
#       seconds of the SAME repetition are highly correlated, so this method
#       very likely leaks train/test information across the split (CV
#       leakage) and is expected to read optimistic.
#   1 = grouped by rep_id (env|variant|workload|repN, carried as each CSV's
#       trailing column by campaign-to-trainsets.py): every row of a given
#       repetition lands in the SAME fold, so no repetition straddles the
#       train/test boundary. If OUT isn't explicitly given, group=1 writes to
#       tier-eval-grouped.tsv instead of tier-eval.tsv, so the two runs don't
#       clobber each other and both stay on disk for comparison.

suppressPackageStartupMessages({ library(e1071) })

args <- commandArgs(trailingOnly = TRUE)
ROOT  <- ifelse(length(args) >= 1, args[1], "results/iada-trainsets")
GROUP <- ifelse(length(args) >= 5, as.logical(as.integer(args[5])), FALSE)
OUT   <- ifelse(length(args) >= 2, args[2],
                 file.path(ROOT, if (GROUP) "tier-eval-grouped.tsv" else "tier-eval.tsv"))
K    <- ifelse(length(args) >= 3, as.integer(args[3]), 5L)
SEED <- ifelse(length(args) >= 4, as.integer(args[4]), 42L)
set.seed(SEED)

LABEL <- c(cpu100 = "cpu", memory100 = "mem", disk100 = "disk",
           net100 = "net", cache100 = "cache", regime100 = "regime")
# the campaign 'train' split = host (bare+container); 'test-vm' split = vm-guest
ENV_SPLIT <- c(host = "train", vm = "test-vm")

read_split <- function(dir) {
  frames <- list()
  for (f in list.files(dir, pattern = "\\.csv$", full.names = TRUE)) {
    lab <- LABEL[[sub("\\.csv$", "", basename(f))]]; if (is.null(lab)) next
    raw <- read.csv2(f, sep = ";", header = FALSE, stringsAsFactors = FALSE)
    # last column is rep_id (a string, e.g. "bare|v3.3|app10_search|rep2"), if
    # present -- campaign-to-trainsets.py always emits it now; older CSVs
    # without it fall back to a synthetic per-row rep_id (= no grouping benefit,
    # but group=1 still runs instead of erroring).
    last <- raw[[ncol(raw)]]
    has_rep_id <- is.character(last) && any(grepl("|", last, fixed = TRUE))
    if (has_rep_id) {
      rep_id <- as.character(last)
      feat <- raw[, -ncol(raw), drop = FALSE]
    } else {
      rep_id <- as.character(seq_len(nrow(raw)))
      feat <- raw
    }
    d <- feat
    d[] <- lapply(d, function(x) suppressWarnings(as.numeric(as.character(x))))
    ok <- complete.cases(d)
    d <- d[ok, , drop = FALSE]; rep_id <- rep_id[ok]; if (nrow(d) == 0) next
    d$category <- lab
    d$rep_id <- rep_id
    frames[[length(frames) + 1]] <- d
  }
  out <- do.call(rbind, frames); out$category <- factor(out$category); out
}

fit_svm <- function(tr) {
  tr <- tr[, setdiff(names(tr), "rep_id"), drop = FALSE]  # never a feature
  tryCatch(svm(category ~ ., data = tr, type = "C-classification",
               nu = 0.10, scale = TRUE, kernel = "polynomial"),
           error = function(e) svm(category ~ ., data = tr, type = "C-classification",
                                   nu = 0.10, scale = FALSE, kernel = "polynomial"))
}

macro_f1 <- function(pred, true, lvls) mean(sapply(lvls, function(c) {
  tp <- sum(pred == c & true == c); fp <- sum(pred == c & true != c); fn <- sum(pred != c & true == c)
  prec <- if (tp + fp > 0) tp/(tp+fp) else 0; rec <- if (tp + fn > 0) tp/(tp+fn) else 0
  if (prec + rec > 0) 2*prec*rec/(prec+rec) else 0
}))

cv_eval <- function(d, k, group = FALSE) {
  lvls <- levels(d$category)
  if (group) {
    # every row of a given rep_id -> the SAME fold, so no repetition straddles
    # train/test (fixes the CV-leakage finding: adjacent 1-second samples of
    # one repetition are highly correlated, and a flat row-level shuffle was
    # letting the model see near-duplicates of its own test rows at train time).
    ids <- unique(d$rep_id)
    id_fold <- sample(rep(1:k, length.out = length(ids)))
    names(id_fold) <- ids
    folds <- unname(id_fold[d$rep_id])
  } else {
    folds <- sample(rep(1:k, length.out = nrow(d)))
  }
  pred <- factor(rep(NA, nrow(d)), levels = lvls)
  for (i in 1:k) {
    tr <- d[folds != i, , drop = FALSE]; te <- d[folds == i, , drop = FALSE]
    if (length(unique(tr$category)) < 2) next
    m <- fit_svm(tr)
    feat <- setdiff(names(te), c("category", "rep_id"))
    pred[folds == i] <- factor(predict(m, te[, feat, drop = FALSE]), levels = lvls)
  }
  ok <- !is.na(pred)
  list(acc = mean(pred[ok] == d$category[ok]),
       f1  = macro_f1(pred[ok], d$category[ok], lvls),
       recall = sapply(lvls, function(c) { m <- d$category == c & ok
         if (sum(m) > 0) mean(pred[m] == c) else NA }),
       lvls = lvls)
}

rows <- c("tier\tenv\tmetric\tclass\tvalue"); head <- list()
for (tier in c("T1", "A", "B")) {
  for (en in names(ENV_SPLIT)) {
    dir <- file.path(ROOT, tier, ENV_SPLIT[[en]]); if (!dir.exists(dir)) next
    d <- read_split(dir)
    r <- cv_eval(d, K, group = GROUP)
    cat(sprintf("\n=== Tier %s — env %s (%d-fold %sCV, n=%d, classes=%s) ===\n",
                tier, en, K, if (GROUP) "grouped-by-rep " else "", nrow(d),
                paste(r$lvls, collapse = ",")))
    cat(sprintf("  accuracy=%.3f  macro-F1=%.3f\n", r$acc, r$f1))
    for (c in r$lvls) cat(sprintf("    recall[%-6s]=%.3f\n", c, r$recall[[c]]))
    rows <- c(rows, sprintf("%s\t%s\taccuracy\t-\t%.4f", tier, en, r$acc),
                    sprintf("%s\t%s\tmacro_f1\t-\t%.4f", tier, en, r$f1))
    for (c in r$lvls) rows <- c(rows, sprintf("%s\t%s\trecall\t%s\t%.4f", tier, en, c, r$recall[[c]]))
    head[[paste(tier, en)]] <- c(acc = r$acc, f1 = r$f1)
  }
}
writeLines(rows, OUT)
cat(sprintf("\n[wrote %s]\n\n=== F13 headline: classifier quality per tier x env (within-env CV) ===\n", OUT))
for (k in names(head)) cat(sprintf("  %-8s  acc=%.3f  macroF1=%.3f\n", k, head[[k]]["acc"], head[[k]]["f1"]))

# ─── host→VM TRANSFER (no per-domain retrain) ────────────────────────────────
# The "train once on the host, deploy directly to the VM" scenario. Unlike the
# within-env CV above, this exposes which metric set survives the deployment
# shift when the classifier is NOT retrained in the target env.
# Disjoint-by-deployment split (train on host, test on VM) -- not subject to
# the row-level CV leakage mechanism above, so GROUP does not change this
# section's method (brief C2.3: re-run only because the trainset CSVs
# changed, not because the transfer-gate methodology needed a fix). Always
# writes to the SAME name regardless of GROUP, so a group=1 run doesn't
# silently duplicate this file under a different name.
TOUT <- ifelse(length(args) >= 6, args[6], file.path(ROOT, "tier-eval-transfer.tsv"))
COUT <- ifelse(length(args) >= 7, args[7], file.path(ROOT, "tier-eval-confusion.tsv"))
trows <- c("tier\tmetric\tclass\tvalue"); thead <- list()
crows <- c("tier\ttrue\tpredicted\tcount")
cat("\n=== host-trained -> VM-tested TRANSFER (no per-domain retrain; GROUP does not apply here) ===\n")
for (tier in c("T1", "A", "B")) {
  trd <- file.path(ROOT, tier, "train"); ted <- file.path(ROOT, tier, "test-vm")
  if (!dir.exists(trd) || !dir.exists(ted)) next
  tr <- read_split(trd); te <- read_split(ted)
  lvls <- levels(tr$category); te$category <- factor(te$category, levels = lvls)
  m <- fit_svm(tr); feat <- setdiff(names(te), c("category", "rep_id"))
  pred <- factor(predict(m, te[, feat, drop = FALSE]), levels = lvls)
  acc <- mean(pred == te$category); f1 <- macro_f1(pred, te$category, lvls)
  trows <- c(trows, sprintf("%s\taccuracy\t-\t%.4f", tier, acc),
                    sprintf("%s\tmacro_f1\t-\t%.4f", tier, f1))
  cat(sprintf("  Tier %s: VM accuracy=%.3f  macro-F1=%.3f\n", tier, acc, f1))
  for (c in lvls) {
    mask <- te$category == c; rec <- if (sum(mask) > 0) mean(pred[mask] == c) else NA
    tp <- sum(pred == c & te$category == c); fp <- sum(pred == c & te$category != c)
    prec <- if (tp + fp > 0) tp / (tp + fp) else NA
    trows <- c(trows, sprintf("%s\trecall\t%s\t%.4f", tier, c, rec),
                      sprintf("%s\tprecision\t%s\t%.4f", tier, c, prec))
    cat(sprintf("    recall[%-6s]=%.3f  precision[%-6s]=%.3f\n", c, rec, c, prec))
  }
  # Full confusion matrix (true x predicted), every cell, zeros included.
  for (ctrue in lvls) for (cpred in lvls) {
    n <- sum(te$category == ctrue & pred == cpred)
    crows <- c(crows, sprintf("%s\t%s\t%s\t%d", tier, ctrue, cpred, n))
  }
}
writeLines(trows, TOUT)
writeLines(crows, COUT)
cat(sprintf("[wrote %s]\n[wrote %s]\n", TOUT, COUT))
