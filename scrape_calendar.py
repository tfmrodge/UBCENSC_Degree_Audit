# -*- coding: utf-8 -*-
"""
Created on Thu Jul  2 12:46:46 2026

@author: Timot
"""

import argparse

from scraper.models import Requirement
from scraper.calendar_scraper import CalendarScraper
from scraper.parser import CalendarParser
from scraper.csv_exporter import CSVExporter
from scraper.complementary_studies_parser import ComplementaryStudiesParser

def run_scraper(
    url: str,
    calendar_year: str = "2026-2027",
    program: str = "ENSC",
    output_dir: str = "output",
    complementary_url: str | None = None
):
    scraper = CalendarScraper()
    parser = CalendarParser()
    exporter = CSVExporter(output_dir=output_dir)

    print("Downloading calendar page...")
    html = scraper.download(url)

    print("Parsing calendar page...")
    package = parser.parse(
        html=html,
        calendar_year=calendar_year,
        program=program
    )

    if complementary_url is not None:
        print("Downloading complementary studies page...")
        complementary_html = scraper.download(complementary_url)

        print("Parsing complementary studies page...")
        complementary_parser = ComplementaryStudiesParser(
            base_parser=parser
        )

        complementary_groups = complementary_parser.parse(
            html=complementary_html,
            program=program,
            calendar_year=calendar_year,
            program_type="All"
        )

        print(
            f"Complementary Studies groups found: "
            f"{len(complementary_groups)}"
        )

        package.requirement_groups.extend(complementary_groups)

        for group in complementary_groups:
            package.requirements.append(
                Requirement(
                    id=group.group_id,
                    name=group.label,
                    courses=group.courses
                )
            )

    print("Exporting CSV files...")
    exporter.export(package)

    print()
    print("Done.")
    print(f"Program: {package.program}")
    print(f"Calendar year: {package.calendar_year}")
    print(f"Program blocks found: {len(package.program_blocks)}")
    print(f"Requirement groups found: {len(package.requirement_groups)}")
    print(f"Footnotes found: {len(package.footnotes)}")
    print(f"Output directory: {output_dir}")

    return package


def main():
    arg_parser = argparse.ArgumentParser(
        description="Scrape a UBC Calendar page and export requirement CSV files."
    )

    arg_parser.add_argument(
        "url",
        help="UBC Calendar URL to scrape"
    )

    arg_parser.add_argument(
        "--calendar-year",
        default="2026-2027",
        help="Calendar year label, e.g. 2023-2024, 2024-2025, 2025-2026, 2026-2027"
    )

    arg_parser.add_argument(
        "--program",
        default="ENSC",
        help="Program code, e.g. ENSC"
    )

    arg_parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory where CSV files will be written"
    )
    
    arg_parser.add_argument(
        "--complementary-url",
        default=None,
        help="Optional EOAS Complementary Studies URL"
    )

    args = arg_parser.parse_args()

    run_scraper(
        url=args.url,
        calendar_year=args.calendar_year,
        program=args.program,
        output_dir=args.output_dir,
        complementary_url=args.complementary_url
    )


if __name__ == "__main__":
    main()