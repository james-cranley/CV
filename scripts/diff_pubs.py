#!/usr/bin/env python3
"""
Diff uncommented \\cvpub entries in cv/publications.tex against an ORCID-derived .bib.

Emits JSON to stdout with four buckets:
  - candidate_pairings: CV preprint-ish entry probably-now-published as an ORCID entry,
    matched by author overlap (titles too divergent for string matching).
  - changed:            same paper (DOI or title match) but metadata differs
                        (typically preprint -> published with title kept).
  - new:                ORCID entries with no match in the CV. Includes a `suggested_subsection`
                        and a pre-formatted `cvpub_latex` for insertion.
  - missing_from_orcid: CV entries with no match in ORCID.

Matching cascade per entry: DOI -> normalised title -> author-set Jaccard (preprint-ish only).
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import bibtexparser

sys.path.insert(0, str(Path(__file__).parent))
from bib2cv import build_cvpub_entry  # noqa: E402
import orcid_history  # noqa: E402


# ---------------------------------------------------------------------------
# normalisation helpers
# ---------------------------------------------------------------------------

def strip_accents_lower(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold().strip()


def normalise_title(t: str) -> str:
    t = strip_accents_lower(t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def normalise_doi(d: str) -> str:
    if not d:
        return ""
    d = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", d.strip(), flags=re.I)
    return d.casefold()


# ---------------------------------------------------------------------------
# parse cv/publications.tex
# ---------------------------------------------------------------------------

CVSUBSECTION_RE = re.compile(r"\\cvsubsection\{([^}]+)\}")
CVPUB_RE = re.compile(r"^\s*\\cvpub\{(.+)\}\s*$")


def parse_publications_tex(path: str) -> List[Dict]:
    entries = []
    current_subsection: Optional[str] = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.lstrip()
            if stripped.startswith("%"):
                continue
            m_sub = CVSUBSECTION_RE.search(line)
            if m_sub:
                current_subsection = m_sub.group(1).strip()
                continue
            m = CVPUB_RE.match(line)
            if m:
                body = m.group(1)
                entries.append({
                    "subsection": current_subsection,
                    "raw": body,
                    "doi": extract_doi_from_cvpub(body),
                    "title": extract_title_from_cvpub(body),
                    "year": extract_year_from_cvpub(body),
                    "surnames_ordered": extract_surnames_from_cvpub(body),
                    "is_preprintish": is_preprintish(body),
                })
    return entries


def extract_doi_from_cvpub(body: str) -> str:
    m = re.search(r"\\href\{https?://(?:dx\.)?doi\.org/([^}]+)\}\{(?:DOI|Link)\}", body, re.I)
    return normalise_doi(m.group(1)) if m else ""


def extract_year_from_cvpub(body: str) -> Optional[int]:
    m = re.search(r"(?<!\d)((?:19|20|21)\d{2})\.", body)
    return int(m.group(1)) if m else None


def extract_title_from_cvpub(body: str) -> str:
    # After the year marker, title runs until the next ". "
    m = re.search(r"\.\s*(?:19|20|21)\d{2}\.\s*([^.]+)\.", body)
    return m.group(1).strip() if m else ""


def extract_surnames_from_cvpub(body: str) -> List[str]:
    """Return ordered list of author surnames."""
    m = re.search(r"^(.*?)\.\s*(?:19|20|21)\d{2}\.", body)
    if not m:
        return []
    author_block = m.group(1)
    author_block = re.sub(r"\\textbf\{([^}]*)\}", r"\1", author_block)
    author_block = re.sub(r"\\emph\{([^}]*)\}", r"\1", author_block)
    author_block = re.sub(r"\\textit\{([^}]*)\}", r"\1", author_block)
    author_block = re.sub(r"\\#", "", author_block)
    author_block = re.sub(r"[\*]+", "", author_block)
    surnames = []
    for chunk in (c.strip() for c in author_block.split(",")):
        if not chunk:
            continue
        tokens = chunk.split()
        if not tokens:
            continue
        surname = tokens[0] if len(tokens) == 1 else " ".join(tokens[:-1])
        surnames.append(surname.strip())
    return surnames


def is_preprintish(body: str) -> bool:
    if re.search(r"under review", body, re.I):
        return True
    if "preprint" in body.lower():
        return True
    doi = extract_doi_from_cvpub(body)
    return doi.startswith("10.1101/")


# ---------------------------------------------------------------------------
# parse ORCID-derived .bib
# ---------------------------------------------------------------------------

def parse_bib(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        db = bibtexparser.load(f)
    out = []
    for e in db.entries:
        title = (e.get("title") or "").strip()
        # Strip leading/trailing braces that bibtex often wraps titles in
        title = re.sub(r"^\{+|\}+$", "", title).strip()
        out.append({
            "doi": normalise_doi(e.get("doi", "")),
            "title": title,
            "year": parse_year(e.get("year", "")),
            "surnames_ordered": bib_surnames_ordered(e.get("author", "")),
            "journal": (e.get("journal") or e.get("journaltitle") or "").strip(),
            "bib_entry": e,
        })
    return out


def parse_year(s: str) -> Optional[int]:
    m = re.search(r"(?:19|20|21)\d{2}", s or "")
    return int(m.group(0)) if m else None


def bib_surnames_ordered(author_field: str) -> List[str]:
    if not author_field:
        return []
    authors = re.split(r"\s+and\s+", author_field.strip())
    surnames = []
    for a in authors:
        a = a.strip()
        if not a:
            continue
        if "," in a:
            surname = a.split(",", 1)[0].strip()
        else:
            tokens = a.split()
            surname = tokens[-1] if tokens else ""
        if surname:
            surnames.append(surname)
    return surnames


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------

def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def surname_set(ordered: List[str]) -> Set[str]:
    return {strip_accents_lower(s) for s in ordered if s}


def diff(cv_entries: List[Dict], bib_entries: List[Dict], pairing_threshold: float) -> Dict:
    matched_cv: Set[int] = set()
    matched_bib: Set[int] = set()
    changed: List[Dict] = []

    # 1. DOI match
    for i, cv in enumerate(cv_entries):
        if not cv["doi"]:
            continue
        for j, b in enumerate(bib_entries):
            if j in matched_bib:
                continue
            if b["doi"] and b["doi"] == cv["doi"]:
                matched_cv.add(i)
                matched_bib.add(j)
                break

    # 2. Title match (catches preprint->published when title kept)
    for i, cv in enumerate(cv_entries):
        if i in matched_cv:
            continue
        cv_norm = normalise_title(cv["title"])
        if not cv_norm:
            continue
        for j, b in enumerate(bib_entries):
            if j in matched_bib:
                continue
            if normalise_title(b["title"]) == cv_norm:
                matched_cv.add(i)
                matched_bib.add(j)
                reason = None
                if cv["doi"] and b["doi"] and cv["doi"] != b["doi"]:
                    reason = "doi_differs_title_same"
                elif cv["is_preprintish"] and b.get("journal"):
                    reason = "preprint_now_published"
                if reason:
                    changed.append({"cv": cv, "bib": b, "reason": reason})
                break

    # 3. Author-overlap pairing (preprint-ish unmatched CV only)
    candidate_pairings: List[Dict] = []
    for i, cv in enumerate(cv_entries):
        if i in matched_cv or not cv["is_preprintish"]:
            continue
        cv_set = surname_set(cv["surnames_ordered"])
        if not cv_set:
            continue
        best: Optional[Tuple[int, float]] = None
        for j, b in enumerate(bib_entries):
            if j in matched_bib:
                continue
            b_set = surname_set(b["surnames_ordered"])
            if not b_set:
                continue
            if b["year"] and cv["year"] and b["year"] < cv["year"]:
                continue
            score = jaccard(cv_set, b_set)
            if score >= pairing_threshold and (best is None or score > best[1]):
                best = (j, score)
        if best:
            j, score = best
            b = bib_entries[j]
            shared = sorted(surname_set(cv["surnames_ordered"]) & surname_set(b["surnames_ordered"]))
            candidate_pairings.append({
                "cv": cv,
                "bib": b,
                "overlap": round(score, 2),
                "shared_count": len(shared),
                "union_count": len(surname_set(cv["surnames_ordered"]) | surname_set(b["surnames_ordered"])),
            })
            matched_cv.add(i)
            matched_bib.add(j)

    new = [bib_entries[j] for j in range(len(bib_entries)) if j not in matched_bib]
    missing = [cv_entries[i] for i in range(len(cv_entries)) if i not in matched_cv]

    return {
        "candidate_pairings": candidate_pairings,
        "changed": changed,
        "new": new,
        "missing_from_orcid": missing,
    }


# ---------------------------------------------------------------------------
# format new entries for insertion
# ---------------------------------------------------------------------------

def suggest_subsection(bib_entry: Dict, me: str, first_n: int = 4) -> str:
    year = bib_entry.get("year")
    if year and year < 2020:
        return "Earlier Work"
    surnames = bib_entry.get("surnames_ordered") or []
    me_norm = strip_accents_lower(me)
    first_n_norm = [strip_accents_lower(s) for s in surnames[:first_n]]
    if me_norm in first_n_norm:
        return "Co-First Author"
    return "Collaborative"


def format_cvpub(bib_entry_dict: Dict, me: str) -> str:
    latex_cv, _, _ = build_cvpub_entry(bib_entry_dict.get("bib_entry", {}), me)
    return latex_cv


# ---------------------------------------------------------------------------
# serialisation
# ---------------------------------------------------------------------------

def serialisable(entry: Dict) -> Dict:
    return {k: v for k, v in entry.items() if k != "bib_entry"}


def to_json(d: Dict) -> Dict:
    return {
        "candidate_pairings": [
            {
                "cv": serialisable(p["cv"]),
                "bib": serialisable(p["bib"]),
                "overlap": p["overlap"],
                "shared_count": p["shared_count"],
                "union_count": p["union_count"],
                "replacement_cvpub_latex": p.get("replacement_cvpub_latex", ""),
            }
            for p in d["candidate_pairings"]
        ],
        "changed": [
            {
                "cv": serialisable(c["cv"]),
                "bib": serialisable(c["bib"]),
                "reason": c["reason"],
                "replacement_cvpub_latex": c.get("replacement_cvpub_latex", ""),
            }
            for c in d["changed"]
        ],
        "new": [serialisable(b) for b in d["new"]],
        "missing_from_orcid": [serialisable(c) for c in d["missing_from_orcid"]],
    }


def main():
    ap = argparse.ArgumentParser(description="Diff publications.tex against an ORCID-derived .bib.")
    ap.add_argument("tex", help="Path to cv/publications.tex")
    ap.add_argument("bib", help="Path to ORCID-derived .bib")
    ap.add_argument("--me", default="Cranley", help="Your surname (default: Cranley)")
    ap.add_argument("--pairing-threshold", type=float, default=0.6,
                    help="Jaccard threshold for author-overlap pairing (default: 0.6)")
    ap.add_argument("--first-n", type=int, default=4,
                    help="Co-First if you appear in first N authors (default: 4)")
    ap.add_argument("--history", default=None,
                    help="Path to history JSON. If set, records this query and "
                         "annotates `new` entries with their prior decision "
                         "(if any). History is loaded/updated but only writes "
                         "the query record; decisions are written by the skill "
                         "after the user confirms them.")
    args = ap.parse_args()

    cv = parse_publications_tex(args.tex)
    bib = parse_bib(args.bib)
    d = diff(cv, bib, args.pairing_threshold)

    # Decorate new entries with subsection suggestion + formatted cvpub
    for entry in d["new"]:
        entry["suggested_subsection"] = suggest_subsection(entry, args.me, args.first_n)
        entry["cvpub_latex"] = format_cvpub(entry, args.me)

    # Annotate `new` entries with the last decision recorded for their DOI,
    # and record this query in the history audit trail.
    if args.history:
        history = orcid_history.load(args.history)
        orcid_history.record_query(history, [b["doi"] for b in bib if b["doi"]])
        for entry in d["new"]:
            prior = orcid_history.get_prior_decision(history, entry["doi"])
            entry["prior_decision"] = prior  # None or {date, action, subsection}
        orcid_history.save(history, args.history)

    # Decorate changed entries with their replacement cvpub
    for c in d["changed"]:
        c["replacement_cvpub_latex"] = format_cvpub(c["bib"], args.me)

    # Decorate candidate pairings with the proposed replacement
    for p in d["candidate_pairings"]:
        p["replacement_cvpub_latex"] = format_cvpub(p["bib"], args.me)

    print(json.dumps(to_json(d), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
