# label-app16-under-references.R -- how is the regime workload labelled when the
# oracle reference classifier has no `regime` class?
#
# jsa-sim-rerun-brief.md Phase 4, verification item 1: tier B's classifier has 6
# classes (the 5 canonical ones + `regime`); T1's and A's have 5. When B's
# placements are re-scored against a T1 or A reference, B's regime workload
# (app16_cpu_oversub) must receive one of the five canonical labels. The brief's
# instruction is to document which, NOT to add special handling.
#
# This replicates exactly what MLClassifier.getMLClass does per row -- load the
# reference's own training frame, load its svm_model.rda, predict each trace row
# -- so the labels here are the labels the simulator actually used.
#
#   Rscript bench/iada/scripts/label-app16-under-references.R <rda-root> <trees-root>

args <- commandArgs(trailingOnly = TRUE)
rda_root   <- args[1]
trees_root <- args[2]
lib        <- Sys.getenv("R_LIBS_IADA", unset = "/home/norodell/Documents/R-lib-iada")
.libPaths(c(lib, .libPaths()))
suppressMessages({ library(e1071); library(dplyr) })

WORKLOAD <- "app16_cpu_oversub"
PATTERNS <- c("con", "dec", "inc", "osc")

for (tier in c("T1", "A", "B")) {
  project_folder_inside <- paste0(rda_root, "/", tier, "/")
  training_dataset_folder <- paste0(project_folder_inside, "forced/")
  firstTime <- 1; firstTimeK <- 1

  source(paste0(project_folder_inside, "input_dataset.R"))
  total <- input_dataset(training_dataset_folder)
  source(paste0(project_folder_inside, "misc.R"))
  source(paste0(project_folder_inside, "cpd.R"))
  source(paste0(project_folder_inside, "kmeans.R"))
  source(paste0(project_folder_inside, "svm.R"))

  feat_cols <- setdiff(names(total), "category")
  cat("\n=== reference classifier: tier ", tier,
      "  (", length(feat_cols), " features, ",
      length(levels(factor(total$category))), " classes: ",
      paste(levels(factor(total$category)), collapse = "/"), ")\n", sep = "")

  all_lbl <- c()
  for (pat in PATTERNS) {
    f <- paste0(trees_root, "/tree-", tier, "-vm-guest/vm-guest/v3.3/source/",
                WORKLOAD, "/", pat, ".csv")
    if (!file.exists(f)) { cat("  missing:", f, "\n"); next }
    tr <- read.csv2(f, sep = ";", header = FALSE)
    tr <- tr[, seq_len(length(feat_cols)), drop = FALSE]
    tr <- setNames(as.data.frame(lapply(tr, as.integer)), feat_cols)
    lbl <- as.character(predict(modelo_svm, tr))
    all_lbl <- c(all_lbl, lbl)
    tb <- table(lbl)
    cat("  ", WORKLOAD, "/", pat, ".csv  (", nrow(tr), " rows): ",
        paste(sprintf("%s=%d", names(tb), as.integer(tb)), collapse = "  "), "\n", sep = "")
  }
  tb <- table(all_lbl)
  cat("  ALL PATTERNS POOLED: ",
      paste(sprintf("%s=%d (%.1f%%)", names(tb), as.integer(tb),
                    100 * as.integer(tb) / sum(tb)), collapse = "  "), "\n", sep = "")
}
