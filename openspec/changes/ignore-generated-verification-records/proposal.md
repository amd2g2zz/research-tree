# Exclude Generated Verification Records

## Why

Local test stdout, elapsed times, command receipts, coverage reports, and tool
caches are reproducible execution by-products. Tracking them causes noisy
cross-platform diffs and merge conflicts without making the tested behavior
more trustworthy.

## What Changes

- Reserve `.research-tree/verification-runs/` for local verification output.
- Ignore generated verification output, receipts, reports, caches, profiles,
  and editor/index state with precise path and filename rules.
- Reject newly added generated verification records in a pull request even if
  they were force-added despite `.gitignore`.
- Prevent receipt generators from writing under tracked OpenSpec evidence
  directories.

## Non-Goals

- Do not ignore or remove hand-authored OpenSpec documents, semantic fixtures,
  schemas, redacted release evidence, or evaluation source assets.
- Do not remove currently tracked historical verification artifacts in this
  change; their registry references require separately reviewable migrations.
- Do not replace required CI checks with local metadata.
