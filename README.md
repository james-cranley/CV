# Curriculum vitae

Academic CV, authored in LaTeX and compiled locally with XeLaTeX on macOS. The rendered `cv.pdf` in the root of this repo is the version of record.

## Prerequisites (see also [`minimal-tex`](https://github.com/james-cranley/minimal-tex)

[BasicTeX](https://www.tug.org/mactex/morepackages.html) on macOS:

```bash
brew install --cask basictex
```

Open a new shell after install so `xelatex` and `latexmk` are on `PATH`.

## One-time setup

BasicTeX ships a minimal TeX Live, so install the extra LaTeX packages this CV depends on:

```bash
sudo tlmgr update --self
sudo tlmgr install fontawesome sourcesanspro tcolorbox hanging unicode-math \
                   enumitem ragged2e setspace xifthen
```

If a later compile complains about a missing `.sty`, `sudo tlmgr install <name>` and re-run.

Then make the bundled FontAwesome glyph font visible to fontspec — on macOS that means dropping it into `~/Library/Fonts/`, because fontspec resolves un-pathed font names through CoreText, which only scans the OS font folders:

```bash
cp fonts/FontAwesome.ttf ~/Library/Fonts/
```

Use `cp`, not `ln -s`; CoreText doesn't index symlinked font files.

## Compiling

One-shot build:

```bash
latexmk -xelatex -interaction=nonstopmode cv.tex
```

Or, from Claude Code, run `/compile-cv` — the skill at `.claude/skills/compile-cv/SKILL.md` refreshes the footer month/year stamp in `cv.tex` if it's stale and then runs the same `latexmk` command, surfacing the relevant log tail on failure.

Live preview while editing — recompiles on save, opens `cv.pdf` in Preview:

```bash
latexmk -xelatex -pvc -interaction=nonstopmode cv.tex
```

Clean intermediate files:

```bash
latexmk -C
```

## Project structure

```
cv.tex                    Document root
academic-cv.cls           Class file (locally patched, see below)
cv/                       Per-section content: education, clinical, research, ...
publications.bib          BibTeX entries
fonts/                    Bundled Roboto + FontAwesome TTFs
cv.pdf                    Compiled output (committed; rebuilt by latexmk)
scripts/                  Helpers for refreshing publications (see below)
.claude/skills/           Repo-local Claude Code skills
.venv/                    Python virtualenv for scripts/ (gitignored, auto-created on first use)
build/                    Intermediate artifacts from scripts/ (gitignored)
```

## Updating publications

The Selected Publications section is refreshed by diffing `cv/publications.tex` against the ORCID record (`0000-0002-0408-5801`), with the H-index and total citations pulled from OpenAlex. The mechanics live in `scripts/`:

- `orcid2bib.py` — pulls all ORCID works to a `.bib`.
- `bib2cv.py` — formats a `.bib` entry as a `\cvpub{...}` line in house style (bolds the author surname, italicises the journal, builds the DOI link).
- `diff_pubs.py` — parses uncommented `\cvpub{...}` entries from `cv/publications.tex`, diffs against the ORCID `.bib`, and emits four buckets: `new`, `changed` (e.g., preprint→published where the title was kept), `candidate_pairings` (preprint→published where the title was rewritten, paired by author-overlap Jaccard), and `missing_from_orcid`.
- `citations.py` — fetches H-index and total citations from OpenAlex for a given author ID.

The Claude Code skill at `.claude/skills/update-publications/SKILL.md` orchestrates all of these. Invoke it from Claude Code via `/update-publications`: it sets up the venv, runs the diff, walks each bucket interactively (asking which subsection to use and which authors are co-first), applies edits in place, refreshes the banner, and shows a `git diff` before leaving.

First-run venv creation (the skill does this automatically if `.venv/` is missing):

```bash
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
```

Standalone usage of the scripts once `.venv/` exists:

```bash
.venv/bin/python scripts/orcid2bib.py 0000-0002-0408-5801 -o build/orcid.bib
.venv/bin/python scripts/diff_pubs.py cv/publications.tex build/orcid.bib --me Cranley
.venv/bin/python scripts/citations.py A5023528834
```

## Local patches to `academic-cv.cls`

Two lines diverge from the upstream Overleaf template:

- **Line 152** — `\newfontfamily\FA[...]{FontAwesome}` → `\renewfontfamily\FA[...]{FontAwesome.ttf}`. On modern TeX Live, the `fontawesome` package already defines `\FA`, so the class's redefinition has to be `\renew*` to avoid a "command already defined" error.
- **Line 618** — `\vspace{-4.0mm}` at the end of the `cvitems` environment, retuned to `\vspace{+1.0mm}`. The original value was tuned against Source Sans Pro; on TeX Live ≥ 2026 the `sourcesanspro` package is a shim that loads Source Sans 3 (different baseline metrics), and the original pull was too aggressive — entry headings overlapped the bullets above them.
