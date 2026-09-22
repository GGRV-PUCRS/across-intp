  # Approach B (full 15-metric + regime class). Reads the 15-column legacy
  # forced/ CSVs and builds the reference training frame `total` with all 15
  # feature names + the 6th "regime" class. Column order MUST match retrain.R's
  # FEATURES (tier B) and MLClassifier's teste frame.
  input_dataset <- function(folder_source){
    FEAT <- c("netp","nets","blk","mbw","llcmr","llcocc","cpu",
              "schedlat","psi_mem","membw_est","psi_io","schedthr",
              "steal","psp","idle_preempt")
    load_cls <- function(file, label){
      df <- read.csv2(paste(folder_source, file, sep = ""), sep = ";")
      df <- df[, 1:15]
      df <- setNames(df, FEAT)
      df$category <- label
      df
    }
    total <- rbind(
      load_cls("cpu100.csv",    "cpu"),
      load_cls("memory100.csv", "mem"),
      load_cls("disk100.csv",   "disk"),
      load_cls("net100.csv",    "net"),
      load_cls("cache100.csv",  "cache"),
      load_cls("regime100.csv", "regime")
    )
    return(total)
  }
