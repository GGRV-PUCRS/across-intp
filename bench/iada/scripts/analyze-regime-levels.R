#!/usr/bin/env Rscript
# analyze-regime-levels.R -- S8 evidence: what the regime class's level
# assignment actually does, keyed on schedlat (col 8, shipped) vs psp
# (col 14, the documented regime signal).
#
# Replays the MLClassifier inference path offline: SVM-classify every row of
# the tier-B simulation traces, take the regime-labelled rows, and assign
# kmeans levels twice -- once per candidate level column. No simulation run
# needed; this is the level-label pipeline in isolation.
#
# Finding this script exists to reproduce: every training centroid has
# schedlat = 100 (the regime stressor saturates it), so which.max/which.min
# tie-break and the schedlat-keyed levels are cluster-ID artifacts. psp
# orders the centroids consistently; on the 28-trace campaign tree it yields
# low/mod only (hig never fires).
#
#   Rscript bench/iada/scripts/analyze-regime-levels.R \
#       [rda_dir=results/iada-tier-rda/B] [tree=/tmp/tree-B-vm-guest]
suppressMessages(library(e1071))

args <- commandArgs(trailingOnly = TRUE)
rda  <- ifelse(length(args) >= 1, args[[1]], "results/iada-tier-rda/B")
tree <- ifelse(length(args) >= 2, args[[2]], "/tmp/tree-B-vm-guest")

load(file.path(rda, "svm_model.rda"))     # modelo_svm
load(file.path(rda, "regimek.rda"))       # cl_regime
cols <- colnames(modelo_svm$SV)

cat("regime centroids on the two candidate level columns:\n")
print(round(cl_regime$centers[, c(8, 14)], 1))
cat("cluster sizes:", cl_regime$size, "\n\n")

files <- Sys.glob(file.path(tree, "*/v3.3/source/*/*.csv"))
if (!length(files)) files <- Sys.glob(file.path(tree, "v3.3/*/source/*/*.csv"))
stopifnot(length(files) > 0)
rows <- do.call(rbind, lapply(files, function(f) read.csv2(f, header = FALSE)))
rows <- as.data.frame(lapply(rows, as.numeric)); names(rows) <- cols

pred <- predict(modelo_svm, rows)
cat("SVM class distribution over", nrow(rows), "trace rows:\n"); print(table(pred))

reg <- rows[pred == "regime", , drop = FALSE]
levels_via <- function(var) {
  ctr <- cl_regime$centers
  hig <- as.integer(which.max(ctr[, var])); low <- as.integer(which.min(ctr[, var]))
  mod <- setdiff(seq_len(nrow(ctr)), c(low, hig)); if (!length(mod)) mod <- -1L
  d <- as.matrix(dist(rbind(ctr, reg)))
  d <- d[-seq_len(nrow(ctr)), seq_len(nrow(ctr)), drop = FALSE]
  a <- max.col(-d)
  ifelse(a == low, "low", ifelse(a == mod, "mod", "hig"))
}
cat("\nregime rows:", nrow(reg), "\n")
cat("levels keyed on schedlat (col 8, shipped -- tie-break artifacts):\n")
print(table(factor(levels_via(8), c("low", "mod", "hig"))))
cat("levels keyed on psp (col 14, S8):\n")
print(table(factor(levels_via(14), c("low", "mod", "hig"))))
