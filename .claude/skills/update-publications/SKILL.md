---
name: update-publications
description: Refresh cv/publications.tex by diffing against the user's ORCID record. Walks candidate preprint→published pairings, changed entries, and new candidates interactively; updates the H-index / total citations banner from OpenAlex.
---

# update-publications

Refreshes `cv/publications.tex` by comparing it against the user's ORCID record and the OpenAlex citation stats.

User constants:
- ORCID: `0000-0002-0408-5801`
- Surname (for highlighting + first-N heuristic): `Cranley`

All shell commands below assume the repo root as cwd.

## Step 1 — Environment

If `.venv/` is missing in the repo root, create it and install deps:

```bash
python3 -m venv .venv && .venv/bin/pip install -q -r scripts/requirements.txt
```

If `.venv/` already exists, skip this. All subsequent Python uses `.venv/bin/python`.

## Step 2 — Fetch ORCID works

```bash
mkdir -p build && .venv/bin/python scripts/orcid2bib.py 0000-0002-0408-5801 -o build/orcid.bib
```

## Step 3 — Diff against publications.tex

```bash
.venv/bin/python scripts/diff_pubs.py cv/publications.tex build/orcid.bib --me Cranley --history scripts/orcid_history.json > build/diff.json
```

The `--history` flag points at a persistent JSON log of past decisions (created on first run). On every invocation this file is updated with:
- An entry in `queries[]` recording today's date and every DOI returned by ORCID.
- For each item in the `new` bucket of `build/diff.json`, a `prior_decision` field is attached: either `null` (never seen before) or `{date, action, subsection}` from the most recent prior decision.

Read `build/diff.json`. It contains four arrays:
- `candidate_pairings` — CV preprint-ish entries paired by author-overlap to an ORCID published entry (titles too divergent for string match).
- `changed` — DOI- or title-matched entries with metadata differences (most often preprint→published with title kept).
- `new` — ORCID entries with no plausible match in the CV. Each carries `suggested_subsection`, `cvpub_latex`, and `prior_decision`.
- `missing_from_orcid` — CV entries with no match in ORCID. Informational only.

Walk the buckets in the order below. Track all approved insertions/replacements in memory; apply them in one pass at Step 8.

## Step 4 — Walk `candidate_pairings` first

For each pairing, show the user both sides and confirm. Use this format:

> Preprint in CV:
> &nbsp;&nbsp;`{cv.title}` ({cv.year}, DOI `{cv.doi}`)
> 
> Possibly now published as (from ORCID):
> &nbsp;&nbsp;`{bib.title}` (*{bib.journal}* {bib.year}, DOI `{bib.doi}`)
> 
> Shared authors: {shared_count}/{union_count} ({overlap*100:.0f}%)
> 
> Are these the same paper? If yes, I'll replace the preprint with the published version (same subsection).

If **yes**: queue a *replacement* — the new line is `replacement_cvpub_latex`; the target line is the `\cvpub{...}` whose body equals `cv.raw`; the subsection stays as `cv.subsection`.

If **no**: leave the CV entry alone. Re-queue the ORCID entry as a `new` candidate to ask about in Step 6.

## Step 5 — Walk `changed`

For each entry, show:

> CV entry: `{cv.title}` ({cv.year}, DOI `{cv.doi}`)
> ORCID has: `{bib.title}` (*{bib.journal}* {bib.year}, DOI `{bib.doi}`)
> Reason: `{reason}`
> 
> Update this entry?

If yes: queue a replacement using `replacement_cvpub_latex` in the same subsection.

## Step 6 — Walk `new`

Partition entries that survived Steps 4–5 (plus any re-queued from Step 4) into two groups based on `prior_decision`:

- **Brand new** — `prior_decision` is `null`.
- **Previously skipped** — `prior_decision.action == "skip"`.

### Step 6a — Previously skipped

If any exist, ask the user as **one batched prompt**:

> On `{date}` you chose to keep the following N article(s) unselected. Re-confirm all as skipped, or pick any to include now?
> 
> 1. `{title}` ({year}, *{journal or "preprint"}*) — skipped on `{prior_decision.date}`
> 2. …

Prefer a multi-select question with one option per article. The user's selections become "include now"; unselected ones get a fresh `action: skip` recorded with today's date. For any selected ones, then run the per-entry `Co-First Author` / `Under review` prompts (steps 6b.3–6b.5) before queueing the insertion.

### Step 6b — Brand new

For each brand-new ORCID entry:

1. Show: title, year, journal (or `(preprint)` if none), first 4 authors with `…` if more, DOI.
2. Ask: **Include in Selected Publications?** (y/n).
3. If **yes**, propose `suggested_subsection`. Options: `Co-First Author`, `Collaborative`, `Earlier Work`. User confirms or overrides.
4. If subsection is `Co-First Author`: ask if any other co-first authors should get `*`. Default is just the user. Take an optional comma-separated list of surnames (e.g., `Mach, Jimba`). Apply `*` to the initials group of each matching surname in `cvpub_latex` — for `Cranley J` the bolded form `\textbf{Cranley J}` becomes `\textbf{Cranley J*}`; for others, `Mach L` becomes `Mach L*`.
5. Optional: ask whether to append a `Under review at \textit{Journal}.` line — only if the entry has no `journal` field and the user wants it labelled.
6. Queue insertion with the final latex.

### Step 6c — Record decisions back to history

After Steps 6a + 6b, persist every decision made this run. The helper module exposes a CLI wrapper for one-shot inserts, but for batch use call it from Python:

```bash
.venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, "scripts")
import orcid_history as oh
h = oh.load("scripts/orcid_history.json")
# For each entry decided this run, e.g.:
#   oh.record_decision(h, doi, "skip", subsection=..., title=..., year=..., journal=...)
#   oh.record_decision(h, doi, "select", subsection="Collaborative", title=..., year=..., journal=...)
oh.save(h, "scripts/orcid_history.json")
EOF
```

Always record both selects **and** skips so the log fully reflects this run.

## Step 7 — Walk `missing_from_orcid`

Show the list as informational only. Frame it as:

> The following entries are in your CV but not in your ORCID. They likely need adding to your ORCID rather than removing from the CV. No edits will be made unless you explicitly ask.

Do not modify the file based on this bucket unless the user asks.

## Step 8 — Apply edits

For each queued insertion: place the line **immediately after** the `\begin{cvpubs}` of the chosen subsection. If multiple insertions land in the same subsection, sort them among themselves by year descending before writing.

For each queued replacement: find the line whose body matches the target `cv.raw` (whitespace-tolerant) and replace it. Preserve indentation.

Never touch commented-out (`% \cvpub{...}`) lines. Subsection headers (`\cvsubsection{...}`) and `\begin/\end{cvpubs}` markers stay where they are.

## Step 9 — Update H-index / citations banner

Resolve OpenAlex author ID from ORCID, then fetch stats:

```bash
.venv/bin/python -c "import requests; r=requests.get('https://api.openalex.org/authors/orcid:0000-0002-0408-5801').json(); print(r['id'].rsplit('/',1)[-1])"
```

Run `citations.py` with that ID:

```bash
.venv/bin/python scripts/citations.py <openalex_id>
```

Rewrite the banner line near the top of `cv/publications.tex` (currently around line 12):

```
H-index <h> | Total citations <citations_with_commas> | ORCID \href{https://orcid.org/0000-0002-0408-5801}{0000-0002-0408-5801}
```

Format citations ≥ 1000 with thousands separators (e.g., `1,471`). Preserve the ORCID link unchanged.

## Step 10 — Show diff and confirm

Run `git diff cv/publications.tex` and show it. Ask: keep the changes, or revert?

If revert: `git restore cv/publications.tex`.

If keep: report what changed in one sentence (e.g., "Added 2 new entries to Collaborative, replaced 1 preprint with its published version, updated banner to H-index 14 / 1,612 citations.") and stop.
