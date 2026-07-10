# -*- coding: utf-8 -*-
"""
Created on Thu Jul  2 12:46:07 2026

@author: Timot
"""

# -*- coding: utf-8 -*-
"""
CSV exporter for the UBC ENSC Degree Audit scraper.

This version supports the newer workflow:

Outputs:
- program_blocks.csv
- requirement_groups.csv
- requirement_courses.csv
- footnotes.csv
- footnote_courses.csv
- scrape_summary.csv

It can also optionally write legacy files:
- requirements.csv
- concentrations.csv

Created on Thu Jul 2 2026

@author: Tim Rodgers with MS Copilot
"""

import csv
from pathlib import Path


class CSVExporter:
    """
    Exports a RequirementPackage to CSV files.

    New workflow outputs:
    - program_blocks.csv
    - requirement_groups.csv
    - requirement_courses.csv
    - footnotes.csv
    - footnote_courses.csv
    - scrape_summary.csv

    Optional legacy outputs:
    - requirements.csv
    - concentrations.csv
    """

    def __init__(
        self,
        output_dir="output",
        #write_legacy_files=True
    ):
        self.output_dir = Path(output_dir)
        #self.write_legacy_files = write_legacy_files

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    def export(self, package):
        """
        Export all CSV files for a parsed RequirementPackage.
        """

        self._write_program_blocks(package)
        self._write_requirement_groups(package)
        self._write_requirement_courses(package)
        self._write_footnotes(package)
        self._write_footnote_courses(package)
        self._write_scrape_summary(package)

        # if self.write_legacy_files:
        #     self._write_legacy_requirements(package)
        #     self._write_legacy_concentrations(package)

    def _write_program_blocks(self, package):
        """
        Write program_blocks.csv.

        One row per specialization block, e.g.
        Major or Honours.
        """

        path = self.output_dir / "program_blocks.csv"

        with open(
            path,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:
            writer = csv.writer(f)

            writer.writerow([
                "program",
                "calendar_year",
                "program_type",
                "specialization_code",
                "title",
                "heading_text"
            ])

            for block in package.program_blocks:
                writer.writerow([
                    block.program,
                    block.calendar_year,
                    block.program_type,
                    block.specialization_code,
                    block.title,
                    block.heading_text
                ])

    def _write_requirement_groups(self, package):
        path = self.output_dir / "requirement_groups.csv"
    
        with open(
            path,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:
            writer = csv.writer(f)
    
            writer.writerow([
                "group_id",
                "program",
                "calendar_year",
                "program_type",
                "year_level",
                "requirement_area",
                "option_id",
                "option_name",
                "option_name_raw",
                "theme",
                "is_recommended",
                "label",
                "credits",
                "rule_type",
                "rule_value",
                "rule_subject",
                "include_pattern",
                "exclude_pattern",
                "rule_unit",
                "source_text"
            ])
    
            for group in package.requirement_groups:
                writer.writerow([
                    group.group_id,
                    group.program,
                    group.calendar_year,
                    group.program_type,
                    group.year_level,
                    group.requirement_area,
                    group.option_id,
                    group.option_name,
                    group.option_name_raw,
                    group.theme,
                    group.is_recommended,
                    group.label,
                    group.credits,
                    group.rule_type,
                    group.rule_value,
                    group.rule_subject,
                    group.include_pattern,
                    group.exclude_pattern,
                    group.rule_unit,
                    group.source_text
                ])

    def _write_requirement_courses(self, package):
        path = self.output_dir / "requirement_courses.csv"
    
        with open(
            path,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:
            writer = csv.writer(f)
    
            writer.writerow([
                "group_id",
                "program",
                "calendar_year",
                "program_type",
                "year_level",
                "requirement_area",
                "option_id",
                "option_name",
                "option_name_raw",
                "theme",
                "is_recommended",
                "label",
                "credits",
                "rule_type",
                "rule_value",
                "rule_subject",
                "include_pattern",
                "exclude_pattern",
                "rule_unit",
                'course_code',
                "source_text"
            ])
    
            for group in package.requirement_groups:
                for course in group.courses:
                    writer.writerow([
                        group.group_id,
                        group.program,
                        group.calendar_year,
                        group.program_type,
                        group.year_level,
                        group.requirement_area,
                        group.option_id,
                        group.option_name,
                        group.option_name_raw,
                        group.theme,
                        group.is_recommended,
                        group.label,
                        group.credits,
                        group.rule_type,
                        group.rule_value,
                        group.rule_subject,
                        group.include_pattern,
                        group.exclude_pattern,
                        group.rule_unit,
                        course,
                        group.source_text
                    ])

    def _write_footnotes(self, package):
        """
        Write footnotes.csv.

        Footnotes often contain important requirement rules,
        such as Tools Elective course lists or Area of Concentration
        credit minimums.
        """

        path = self.output_dir / "footnotes.csv"

        with open(
            path,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:
            writer = csv.writer(f)

            writer.writerow([
                "footnote_id",
                "program",
                "calendar_year",
                "program_type",
                "footnote_number",
                "text"
            ])

            for footnote in package.footnotes:
                writer.writerow([
                    footnote.footnote_id,
                    footnote.program,
                    footnote.calendar_year,
                    footnote.program_type,
                    footnote.footnote_number,
                    footnote.text
                ])

    def _write_footnote_courses(self, package):
        """
        Write footnote_courses.csv.

        One row per course extracted from a footnote.
        """

        path = self.output_dir / "footnote_courses.csv"

        with open(
            path,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:
            writer = csv.writer(f)

            writer.writerow([
                "footnote_id",
                "program",
                "calendar_year",
                "program_type",
                "footnote_number",
                "course_code"
            ])

            for footnote in package.footnotes:
                for course in footnote.courses:
                    writer.writerow([
                        footnote.footnote_id,
                        footnote.program,
                        footnote.calendar_year,
                        footnote.program_type,
                        footnote.footnote_number,
                        course
                    ])

    def _write_scrape_summary(self, package):
        """
        Write scrape_summary.csv.

        Useful quick diagnostic file.
        """

        path = self.output_dir / "scrape_summary.csv"

        requirement_course_count = sum(
            len(group.courses)
            for group in package.requirement_groups
        )

        footnote_course_count = sum(
            len(footnote.courses)
            for footnote in package.footnotes
        )

        with open(
            path,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:
            writer = csv.writer(f)

            writer.writerow([
                "program",
                "calendar_year",
                "program_blocks_found",
                "requirement_groups_found",
                "requirement_course_mappings_found",
                "footnotes_found",
                "footnote_course_mappings_found"
            ])

            writer.writerow([
                package.program,
                package.calendar_year,
                len(package.program_blocks),
                len(package.requirement_groups),
                requirement_course_count,
                len(package.footnotes),
                footnote_course_count
            ])