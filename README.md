# Curriculum vitae

Academic CV, authored in LaTeX and compiled locally with XeLaTeX on macOS. The rendered `cv.pdf` in the root of this repo is the version of record.

## Prerequisites

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
cv.tex              Document root
academic-cv.cls     Class file (locally patched, see below)
cv/                 Per-section content: education, clinical, research, ...
publications.bib    BibTeX entries
fonts/              Bundled Roboto + FontAwesome TTFs
profile.png         Header photo
cv.pdf              Compiled output (committed; rebuilt by latexmk)
README.pdf          Upstream class-template documentation (kept for reference)
```

## Local patches to `academic-cv.cls`

Two lines diverge from the upstream Overleaf template:

- **Line 152** — `\newfontfamily\FA[...]{FontAwesome}` → `\renewfontfamily\FA[...]{FontAwesome.ttf}`. On modern TeX Live, the `fontawesome` package already defines `\FA`, so the class's redefinition has to be `\renew*` to avoid a "command already defined" error.
- **Line 618** — `\vspace{-4.0mm}` at the end of the `cvitems` environment, retuned to `\vspace{+1.0mm}`. The original value was tuned against Source Sans Pro; on TeX Live ≥ 2026 the `sourcesanspro` package is a shim that loads Source Sans 3 (different baseline metrics), and the original pull was too aggressive — entry headings overlapped the bullets above them.
