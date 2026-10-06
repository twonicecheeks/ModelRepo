#!/usr/bin/env Rscript
# Optional baseballr export. No package is installed or network call is made
# until this script is run explicitly on the user's machine.
run <- function() {
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2L || length(args) > 21L) {
  stop("Usage: Rscript tools/export_delta_pbp.R NEW_OUTPUT_DIR game_pk [game_pk ...]", call. = FALSE)
}
if (!requireNamespace("baseballr", quietly = TRUE)) {
  stop("Install the optional baseballr R package in your R environment.", call. = FALSE)
}
destination <- path.expand(args[[1]])
if (file.exists(destination)) stop("Output directory already exists.", call. = FALSE)
game_pks <- args[-1]
if (any(!grepl("^[1-9][0-9]{0,14}$", game_pks)) || anyDuplicated(game_pks)) {
  stop("Provide unique positive MLB game_pk identifiers.", call. = FALSE)
}
stage <- tempfile(pattern = ".delta-pbp-", tmpdir = dirname(destination))
if (!dir.create(stage, recursive = TRUE)) stop("Cannot create temporary output directory.", call. = FALSE)
completed <- FALSE
on.exit(if (!completed) unlink(stage, recursive = TRUE), add = TRUE)
for (pk in game_pks) {
  frame <- baseballr::mlb_pbp(as.numeric(pk), add_base_state = TRUE)
  if (is.null(frame) || !nrow(frame)) stop(paste("No PBP returned for", pk), call. = FALSE)
  if (!all(as.character(frame$game_pk) == pk)) stop("Returned game_pk mismatch.", call. = FALSE)
  write.csv(frame, file.path(stage, paste0("pbp_", pk, ".csv")), row.names = FALSE, na = "")
}
if (!file.rename(stage, destination)) stop("Cannot finalize PBP export directory.", call. = FALSE)
completed <- TRUE
cat(sprintf("Saved %d MLB play-by-play CSV files to %s\n", length(game_pks), destination))
}
run()
