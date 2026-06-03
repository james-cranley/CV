#!/usr/bin/env python3
import sys
import argparse
import requests

def main():
    parser = argparse.ArgumentParser(
        description="Fetch H-index and citation count from OpenAlex for a given author ID."
    )
    parser.add_argument("author_id", help="OpenAlex Author ID (e.g., A5023528834)")
    parser.add_argument("-o", "--output", help="Output file to save results (e.g., citations.txt)")
    args = parser.parse_args()

    url = f"https://api.openalex.org/authors/{args.author_id}"

    try:
        r = requests.get(url)
        r.raise_for_status()
        data = r.json()

        name = data.get("display_name", "N/A")
        h_index = data.get("summary_stats", {}).get("h_index", "N/A")
        total_citations = data.get("cited_by_count", "N/A")

        # Prepare tab-separated line
        header = "authorID\tname\th\tcitations\n"
        row = f"{args.author_id}\t{name}\t{h_index}\t{total_citations}\n"

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(header)
                f.write(row)
            print(f"✅ Data written to {args.output}")
        else:
            print(header.strip())
            print(row.strip())

    except requests.exceptions.RequestException as e:
        print("Error fetching data from OpenAlex:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
