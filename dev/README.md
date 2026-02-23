# Dev Folder Policy

Use `dev/` for non-project or transient artifacts only.

## Put here
- Scratch notes
- Temporary experiments
- Local-only debug scripts
- One-off data checks
- Utility scripts not required by runtime/production flow (for example report-build helpers)

## Do not put here
- Production code
- Tests that are part of CI
- Final documentation
- Release assets

When something from `dev/` becomes stable and project-relevant, move it into the main project tree.
