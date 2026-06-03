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

## Step 5 — Offer to publish to GitHub Pages

Only if Step 3 succeeded. Ask the user with the `AskUserQuestion` tool — a single question, `header: "Publish"`, `question: "Push freshly compiled cv.pdf to james-cranley.github.io?"`, options `Yes` / `No`.

If the answer is **No**, skip to Step 6.

If the answer is **Yes**:

1. Capture the absolute path to the freshly built PDF first (`/Users/jamescranley/GitHub/CV/cv.pdf`) — the steps below `cd` away from this repo.
2. `cd ~/GitHub/james-cranley.github.io`.
3. Abort if the pages repo's working tree is dirty: run `git status --porcelain`; if it produces any output, report `Pages repo has uncommitted changes — aborting publish.` and stop. Do not stash, reset, or otherwise touch the user's in-flight work there.
4. `git checkout master` (local clone may currently be on `main`; the remote default is `master`).
5. `git pull --rebase origin master`.
6. Copy the freshly built PDF into place: `cp /Users/jamescranley/GitHub/CV/cv.pdf cv/cv.pdf`.
7. If `git diff --quiet cv/cv.pdf` (exit 0, no change), report `Pages cv.pdf already up to date — nothing to push.` and stop.
8. Otherwise commit and push, using the `<Month> <Year>` value from Step 1:
   ```bash
   git add cv/cv.pdf
   git commit -m "update cv.pdf — <Month> <Year>"
   git push origin master
   ```
9. Report the resulting short SHA, e.g. `Published cv.pdf to GitHub Pages (abc1234).`

## Step 6 — Do not commit (CV repo)

Leave `cv.pdf` modified in this repo's working tree. The user decides whether to commit here. Do not run `git add` or `git commit` in `/Users/jamescranley/GitHub/CV`.

## Notes

- Don't run `latexmk -C` (cleanup) before the build — let `latexmk`'s incremental state speed up repeat compiles.
- If `latexmk` or `xelatex` is missing, tell the user to follow the `Prerequisites` section of `README.md` and stop; do not attempt to install TeX.
