"""Persist per-DOI decisions about whether to include an ORCID work in the CV.

The history file lets the skill say "you skipped these on YYYY-MM-DD, still skip?"
on subsequent runs instead of asking from scratch every time.

Schema (JSON):
  {
    "queries": [
      {"date": "YYYY-MM-DD", "orcid_dois": [doi, ...]}
    ],
    "decisions": {
      "<normalised_doi>": {
        "title": str,
        "year": int | null,
        "journal": str,
        "first_seen": "YYYY-MM-DD",
        "history": [
          {"date": "YYYY-MM-DD", "action": "skip" | "select", "subsection": str | null}
        ]
      }
    }
  }
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import unicodedata
from pathlib import Path
from typing import Optional


def _today() -> str:
    return _dt.date.today().isoformat()


def _normalise_doi(d: str) -> str:
    if not d:
        return ""
    d = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", d.strip(), flags=re.I)
    return d.casefold()


def load(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"queries": [], "decisions": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def save(history: dict, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(history, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def record_query(history: dict, dois: list[str], date: Optional[str] = None) -> None:
    """Append today's ORCID query (list of DOIs found) to the audit trail."""
    date = date or _today()
    norm = [_normalise_doi(d) for d in dois if d]
    history.setdefault("queries", []).append({"date": date, "orcid_dois": norm})


def ensure_decision_record(
    history: dict,
    doi: str,
    title: str = "",
    year: Optional[int] = None,
    journal: str = "",
    date: Optional[str] = None,
) -> dict:
    """Return the decision record for a DOI, creating an empty one if absent."""
    doi = _normalise_doi(doi)
    if not doi:
        raise ValueError("ensure_decision_record requires a non-empty DOI")
    date = date or _today()
    decisions = history.setdefault("decisions", {})
    rec = decisions.get(doi)
    if rec is None:
        rec = {
            "title": title,
            "year": year,
            "journal": journal,
            "first_seen": date,
            "history": [],
        }
        decisions[doi] = rec
    else:
        # Backfill metadata if it was missing
        if not rec.get("title") and title:
            rec["title"] = title
        if rec.get("year") is None and year is not None:
            rec["year"] = year
        if not rec.get("journal") and journal:
            rec["journal"] = journal
    return rec


def get_prior_decision(history: dict, doi: str) -> Optional[dict]:
    """Return the most recent {date, action, subsection} for this DOI, or None."""
    doi = _normalise_doi(doi)
    rec = history.get("decisions", {}).get(doi)
    if not rec or not rec.get("history"):
        return None
    return rec["history"][-1]


def record_decision(
    history: dict,
    doi: str,
    action: str,
    *,
    subsection: Optional[str] = None,
    title: str = "",
    year: Optional[int] = None,
    journal: str = "",
    date: Optional[str] = None,
) -> None:
    """Append a decision event to a DOI's history."""
    if action not in ("skip", "select"):
        raise ValueError(f"action must be 'skip' or 'select', got {action!r}")
    date = date or _today()
    rec = ensure_decision_record(
        history, doi, title=title, year=year, journal=journal, date=date
    )
    rec["history"].append(
        {"date": date, "action": action, "subsection": subsection}
    )


# ---------------------------------------------------------------------------
# CLI: seed history from currently-commented \cvpub lines in publications.tex
# ---------------------------------------------------------------------------

_DOI_RE = re.compile(
    r"\\href\{https?://(?:dx\.)?doi\.org/([^}]+)\}\{(?:DOI|Link)\}", re.I
)
_TITLE_RE = re.compile(r"\.\s*((?:19|20|21)\d{2})\.\s*([^.]+)\.")
_JOURNAL_RE = re.compile(r"\\textit\{([^}]+)\}")
_CVSUB_RE = re.compile(r"\\cvsubsection\{([^}]+)\}")


def _parse_cvpub_metadata(body: str) -> dict:
    doi_m = _DOI_RE.search(body)
    title_m = _TITLE_RE.search(body)
    journal_m = _JOURNAL_RE.search(body)
    return {
        "doi": _normalise_doi(doi_m.group(1)) if doi_m else "",
        "year": int(title_m.group(1)) if title_m else None,
        "title": title_m.group(2).strip() if title_m else "",
        "journal": journal_m.group(1).strip() if journal_m else "",
    }


def seed_from_publications_tex(
    history: dict, tex_path: str | Path, date: Optional[str] = None
) -> int:
    """Record action=skip for every commented-out \\cvpub line in publications.tex.

    Returns the number of decisions added.
    """
    date = date or _today()
    added = 0
    current_section: Optional[str] = None
    for raw_line in Path(tex_path).read_text(encoding="utf-8").splitlines():
        sub_m = _CVSUB_RE.search(raw_line)
        if sub_m:
            current_section = sub_m.group(1).strip()
            continue
        stripped = raw_line.strip()
        if not stripped.startswith("%"):
            continue
        # Drop leading % markers + whitespace
        body = stripped.lstrip("%").lstrip()
        if not body.startswith("\\cvpub{"):
            continue
        # Extract the {...} payload — body may have trailing braces from the line
        inner = body[len("\\cvpub{"):]
        # Trim a trailing } if present
        inner = inner.rstrip()
        if inner.endswith("}"):
            inner = inner[:-1]
        meta = _parse_cvpub_metadata(inner)
        if not meta["doi"]:
            continue
        # Don't overwrite an existing decision
        if history.get("decisions", {}).get(meta["doi"]):
            continue
        record_decision(
            history,
            meta["doi"],
            "skip",
            subsection=current_section,
            title=meta["title"],
            year=meta["year"],
            journal=meta["journal"],
            date=date,
        )
        added += 1
    return added


def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Manage the ORCID-decisions history JSON file."
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    seed = sub.add_parser(
        "seed",
        help="Seed history with action=skip for every commented-out \\cvpub in a tex file.",
    )
    seed.add_argument("history", help="Path to history JSON (created if missing)")
    seed.add_argument("tex", help="Path to cv/publications.tex")
    seed.add_argument("--date", help="Override date (default: today)")

    show = sub.add_parser("show", help="Pretty-print current history")
    show.add_argument("history", help="Path to history JSON")

    args = ap.parse_args()

    if args.cmd == "seed":
        h = load(args.history)
        n = seed_from_publications_tex(h, args.tex, date=args.date)
        save(h, args.history)
        print(f"Seeded {n} skip decisions into {args.history}")
    elif args.cmd == "show":
        h = load(args.history)
        print(json.dumps(h, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()
