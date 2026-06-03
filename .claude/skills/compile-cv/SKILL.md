---
name: compile-cv
description: Refresh the footer month/year if stale, then compile cv.tex to cv.pdf with latexmk + XeLaTeX. Surfaces the relevant log tail on failure.
---

# compile-cv

Compiles `cv.tex` → `cv.pdf` after making sure the footer date stamp matches the current month and year.

All shell commands assume the repo root as cwd.

## Step 1 — Determine current month/year

Use the date from the harness context (`# currentDate`). Format as `<Month> <Year>` with the month spelled out in English (e.g. `June 2026`).

## Step 2 — Reconcile the footer date in `cv.tex`

The footer's left cell is set by the first argument to `\makecvfooter` in `cv.tex`. Currently the call lives around line 64 and reads:

```latex
\makecvfooter
  {June 2026}
  {James Cranley ~~~·~~~ Curriculum Vitae}
  {\thepage}
```

Grep for the `\makecvfooter` block, parse the first `{...}` argument, and compare to the expected `<Month> <Year>`. If they differ, **edit it silently** (no confirmation) to the current value. If they match, do nothing. Report the action taken in one line, e.g. `Footer date already June 2026.` or `Footer date updated May 2026 → June 2026.`

## Step 3 — Compile with latexmk

```bash
latexmk -xelatex -interaction=nonstopmode cv.tex
```

The class file pulls fonts via `fontspec`, so XeLaTeX is required — do not substitute `pdflatex`. `latexmk` will re-run as many passes as it needs.

## Step 4 — Handle outcome

- **Success** (exit 0): report `Built cv.pdf` plus the page count. Use `pdfinfo cv.pdf` if available, otherwise count `/Type /Page` matches in the PDF. A success line example: `Built cv.pdf (5 pages, 0.08 MB).`
- **Failure** (non-zero exit): surface the last ~40 lines of `cv.log` so the user can see the actual TeX error. Do not attempt to auto-fix LaTeX errors — report and stop. Example:

  ```bash
  tail -n 40 cv.log
  ```

## Step 5 — Do not commit

Leave `cv.pdf` modified in the working tree. The user decides whether to commit. Do not run `git add` or `git commit`.

## Notes

- Don't run `latexmk -C` (cleanup) before the build — let `latexmk`'s incremental state speed up repeat compiles.
- If `latexmk` or `xelatex` is missing, tell the user to follow the `Prerequisites` section of `README.md` and stop; do not attempt to install TeX.
