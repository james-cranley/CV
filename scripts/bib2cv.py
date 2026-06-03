#!/usr/bin/env python3
# Converts a .bib to an .xlsx with columns: title, year, author_year, LaTeX_cv, LaTeX, plain
# Optional: --highlight-name SURNAME_INITIALS (e.g., Cranley_J) to bold that author.

import argparse
import re
import unicodedata
from typing import List, Tuple, Optional

import pandas as pd
import bibtexparser


def strip_accents_lower(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold().strip()


def split_highlight_token(token: str) -> Tuple[str, str]:
    parts = token.split("_", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def tokenize_authors(bib_authors_field: str) -> List[str]:
    return [a.strip() for a in re.split(r"\s+and\s+", bib_authors_field.strip()) if a.strip()]


def name_to_surname_given(name: str) -> Tuple[str, str]:
    if "," in name:
        last, given = [p.strip() for p in name.split(",", 1)]
        return last, given
    tokens = name.split()
    if len(tokens) == 1:
        return tokens[0], ""
    return tokens[-1], " ".join(tokens[:-1])


def initials_from_given(given: str) -> str:
    parts = [p for p in re.split(r"\s+", given.strip()) if p]
    initials = []
    for p in parts:
        p_clean = re.sub(r"[^\w\-]", "", p)
        for sub in p_clean.split("-"):
            if sub:
                initials.append(sub[0])
    return "".join(initials).upper()


def format_author(surname: str, given: str, highlight: Optional[Tuple[str, str]]) -> str:
    initials = initials_from_given(given)
    formatted = f"{surname} {initials}" if initials else surname

    if highlight:
        target_surname, target_initials = highlight
        if target_surname:
            s1 = strip_accents_lower(surname)
            s2 = strip_accents_lower(target_surname)
            if s1 == s2:
                if target_initials:
                    if initials.upper().startswith(target_initials.upper()):
                        return r"\textbf{" + formatted + "}"
                else:
                    return r"\textbf{" + formatted + "}"
    return formatted


def format_author_list(author_field: str, highlight_token: Optional[str]) -> str:
    highlight = None
    if highlight_token:
        hs, hi = split_highlight_token(highlight_token)
        highlight = (hs, hi)

    authors = tokenize_authors(author_field)
    formatted_authors = []
    for a in authors:
        surname, given = name_to_surname_given(a)
        formatted_authors.append(format_author(surname, given, highlight))
    return ", ".join(formatted_authors)


def choose_first_nonempty(*vals: str) -> str:
    for v in vals:
        if v:
            return v
    return ""


def extract_year(entry: dict) -> str:
    y = (entry.get("year") or "").strip()
    if re.fullmatch(r"\d{4}", y):
        return y
    for key in ("date", "pubdate", "issued", "year"):
        val = (entry.get(key) or "").strip()
        m = re.search(r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b", val)
        if m:
            return m.group(0)
    return ""


def extract_first_author(entry: dict) -> str:
    author_field = entry.get("author", "")
    if not author_field:
        return ""
    authors = tokenize_authors(author_field)
    if not authors:
        return ""
    surname, _ = name_to_surname_given(authors[0])
    return surname


def build_cvpub_entry(entry: dict, highlight_token: Optional[str]) -> Tuple[str, str, str]:
    """Return (LaTeX_cv, LaTeX, plain_text) versions of the same entry."""
    author_field = entry.get("author", "")
    year = extract_year(entry)
    title = (entry.get("title") or "").strip()
    journal = choose_first_nonempty((entry.get("journal") or "").strip(),
                                    (entry.get("journaltitle") or "").strip())
    volume = (entry.get("volume") or "").strip()
    number = (entry.get("number") or "").strip()
    pages = (entry.get("pages") or "").strip()
    doi = (entry.get("doi") or "").strip()
    url = (entry.get("url") or "").strip()

    authors_fmt = format_author_list(author_field, highlight_token) if author_field else ""

    journal_bits = []
    if journal:
        journal_bits.append(r"\textit{" + journal + "}")
    vol_issue = ""
    if volume and number:
        vol_issue = f"{volume}({number})"
    elif volume:
        vol_issue = f"{volume}"
    if vol_issue:
        journal_bits.append(vol_issue)
    if pages:
        if vol_issue:
            journal_bits[-1] = f"{journal_bits[-1]}: {pages}"
        else:
            journal_bits.append(pages)
    journal_str = ", ".join(journal_bits) + "." if journal_bits else ""

    # Build LaTeX link string
    link_str = ""
    plain_link = ""
    if doi:
        doi_clean = re.sub(r"^https?://doi\.org/", "", doi, flags=re.I)
        full_url = f"https://doi.org/{doi_clean}"
        link_str = r" \href{" + full_url + r"}{DOI}"
        plain_link = full_url
    elif url:
        link_str = r" \href{" + url + r"}{Link}"
        plain_link = url

    # --- Build shared LaTeX content ---
    pieces = []
    if authors_fmt:
        pieces.append(authors_fmt + ".")
    if year:
        pieces.append(f" {year}.")
    if title:
        pieces.append(f" {title}.")
    if journal_str:
        pieces.append(f" {journal_str}")
    if link_str:
        pieces.append(link_str)

    inner = " ".join(pieces).strip()
    inner = re.sub(r"\s+", " ", inner)

    # Two LaTeX variants
    latex_cv = r"\cvpub{" + inner + "}"
    latex_no_cv = inner  # same, but no wrapper

    # --- Build plain text version ---
    plain_entry = re.sub(r"\\textbf{([^}]*)}", r"\1", inner)
    plain_entry = re.sub(r"\\textit{([^}]*)}", r"\1", plain_entry)
    plain_entry = re.sub(r"\\href{[^}]*}{([^}]*)}", plain_link, plain_entry)
    plain_entry = re.sub(r"\\[a-zA-Z]+", "", plain_entry)
    plain_entry = plain_entry.replace("{", "").replace("}", "").strip()

    return latex_cv, latex_no_cv, plain_entry


def main():
    ap = argparse.ArgumentParser(description="Convert .bib to .xlsx with LaTeX and plain text columns.")
    ap.add_argument("bib_path", help="Input .bib file")
    ap.add_argument("xlsx_path", help="Output .xlsx file")
    ap.add_argument("--highlight-name", help="Highlight SURNAME_INITIALS (e.g., Cranley_J, Teichmann_SA)", default=None)
    args = ap.parse_args()

    with open(args.bib_path, "r", encoding="utf-8") as f:
        bib_db = bibtexparser.load(f)

    rows = []
    for e in bib_db.entries:
        title = (e.get("title") or "").strip()
        year = extract_year(e)
        first_author = extract_first_author(e)
        author_year = f"{first_author}{year}" if first_author and year else ""
        latex_cv, latex_no_cv, plain_entry = build_cvpub_entry(e, args.highlight_name)
        rows.append({
            "title": title,
            "year": year,
            "author_year": author_year,
            "LaTeX_cv": latex_cv,
            "LaTeX": latex_no_cv,
            "plain": plain_entry
        })

    df = pd.DataFrame(rows, columns=["title", "year", "author_year", "LaTeX_cv", "LaTeX", "plain"])

    # Sort by year descending, then title ascending
    def year_to_sort(y: str) -> int:
        try:
            return int(y)
        except Exception:
            return -10**9

    df["year_sort"] = df["year"].apply(year_to_sort)
    df = df.sort_values(by=["year_sort", "title"], ascending=[False, True]).drop(columns=["year_sort"])

    df.to_excel(args.xlsx_path, index=False)
    print(f"Wrote {len(df)} rows to {args.xlsx_path}")


if __name__ == "__main__":
    main()
