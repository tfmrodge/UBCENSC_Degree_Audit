# -*- coding: utf-8 -*-
"""
Created on Tue Jul 7 09:23:35 2026

Authors: Tim Rodgers with M365 Copilot.

Parser for ENSC Complementary Studies courses from the EOAS Environmental
Sciences webpage.

This parser appends eligible Complementary Studies course rules directly into
the shared RequirementGroup model so the results are exported to:

- requirement_groups.csv
- requirement_courses.csv

It intentionally does NOT create the minimum-credit requirement, because that
should come from the Academic Calendar curriculum table when possible.
"""

import re
from typing import Optional

from bs4 import BeautifulSoup

from .models import RequirementGroup
from .parser import CalendarParser


COMPLEMENTARY_STUDIES_REQUIREMENT_AREA = "Complementary Studies"


class ComplementaryStudiesParser:
    """
    Parses ENSC Complementary Studies information from the EOAS page.

    This parser focuses on eligible courses and wildcard subject rules such as:
    - All HGSE courses

    It does not currently emit advisor-approval notes or duplicate the
    Complementary Studies minimum-credit rule.
    """

    def __init__(self, base_parser: Optional[CalendarParser] = None):
        if base_parser is None:
            base_parser = CalendarParser()

        self.base_parser = base_parser

    def parse(
        self,
        html: str,
        program: str,
        calendar_year: str,
        program_type: str = "All"
    ) -> list:
        soup = BeautifulSoup(html, "html.parser")

        lines = self._extract_relevant_text_lines(soup)

        groups = self._parse_lines_to_groups(
            lines=lines,
            program=program,
            calendar_year=calendar_year,
            program_type=program_type
        )

        return groups

    def _extract_relevant_text_lines(self, soup) -> list:
        """
        Extract text lines around the ENSC Complementary Studies section.

        Uses text anchors instead of fragile CSS selectors.
        """

        all_text = soup.get_text("\n", strip=True)

        raw_lines = [
            line.strip()
            for line in all_text.splitlines()
            if line.strip()
        ]

        start_index = None

        start_markers = [
            "ENSC Complementary Studies Courses",
            "ENSC Complementary Studies",
        ]

        for i, line in enumerate(raw_lines):
            for marker in start_markers:
                if marker.lower() == line.lower():
                    start_index = i
                    break

            if start_index is not None:
                break

        if start_index is None:
            return []

        stop_markers = [
            "Minor",
            "Course Planning",
            "Career",
            "Useful links",
            "Contact",
            "Degree Requirements",
        ]

        relevant = []

        for i, line in enumerate(raw_lines[start_index:]):
            lower = line.lower()

            if i > 0 and any(marker.lower() == lower for marker in stop_markers):
                break

            relevant.append(line)

        return relevant

    def _parse_lines_to_groups(
        self,
        lines: list[str],
        program: str,
        calendar_year: str,
        program_type: str
    ) -> list:
        groups = []

        current_theme = None
        counter = 1

        for line in lines:
            if self._is_noise_line(line):
                continue

            if self._is_policy_line(line):
                # For now, skip advisor/policy text.
                # Later, this could go to policy_notes.csv.
                continue
            
            if self._is_advising_or_non_requirement_line(line):
                continue

            if self._looks_like_theme_heading(line):
                current_theme = line
                continue

            wildcard_subject = self._extract_subject_wildcard(line)

            if wildcard_subject is not None:
                group = self._make_complementary_group(
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type,
                    counter=counter,
                    theme=current_theme,
                    label=line,
                    rule_type="subject_all",
                    rule_value=None,
                    courses=[f"{wildcard_subject}*"],
                    source_text=line,
                    credits=None
                )

                groups.append(group)
                counter += 1
                continue

            courses = self.base_parser._extract_courses_with_continuations(line)

            if courses:
                group = self._make_complementary_group(
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type,
                    counter=counter,
                    theme=current_theme,
                    label=line,
                    rule_type="complementary_studies_eligible_courses",
                    rule_value=None,
                    courses=courses,
                    source_text=line,
                    credits=None
                )

                groups.append(group)
                counter += 1

        return groups

    def _is_noise_line(self, line: str) -> bool:
        lower = line.lower()

        noise_exact = {
            "environmental sciences",
            "ensc complementary studies courses",
            "ensc complementary studies",
        }

        if lower in noise_exact:
            return True

        if len(line.strip()) == 0:
            return True

        return False

    def _is_policy_line(self, line: str) -> bool:
        """
        Policy lines are useful but not directly machine-auditable.

        These should eventually be exported to policy_notes.csv, not
        requirement_groups.csv.
        """

        lower = line.lower()

        policy_phrases = [
            "students can propose alternative courses",
            "course proposals will be approved",
            "there are two ways to satisfy this requirement",
            "students will be required to complete",
            "all ensc students will be required to complete",
        ]

        return any(phrase in lower for phrase in policy_phrases)

    def _looks_like_theme_heading(self, line: str) -> bool:
        """
        Heuristic for theme headings.

        Theme headings generally:
        - do not contain course codes
        - are not wildcard rules
        - are not policy sentences
        - are not very long
        """

        if self.base_parser._extract_courses_with_continuations(line):
            return False

        if self._extract_subject_wildcard(line) is not None:
            return False

        lower = line.lower()

        if "students" in lower:
            return False

        if "course" in lower and len(line.split()) < 5:
            return False

        if len(line) > 100:
            return False

        if line.endswith("."):
            return False

        return True

    def _extract_subject_wildcard(self, line: str) -> Optional:
        """
        Parse rules like:
        - All HGSE courses

        Returns:
        - HGSE
        """

        match = re.search(
            r"^all\s+([A-Z]{2,5})\s+courses$",
            line.strip(),
            re.IGNORECASE
        )

        if not match:
            return None

        return match.group(1).upper()

    def _make_complementary_group(
        self,
        program: str,
        calendar_year: str,
        program_type: str,
        counter: int,
        theme: Optional[str],
        label: str,
        rule_type: str,
        rule_value: Optional[int],
        courses: list[str],
        source_text: str,
        credits: Optional[float]
    ) -> RequirementGroup:
        group_id = self._make_complementary_group_id(
            program=program,
            calendar_year=calendar_year,
            program_type=program_type,
            counter=counter
        )

        return RequirementGroup(
            group_id=group_id,
            program=program,
            calendar_year=calendar_year,
            program_type=program_type,
            year_level=None,
            label=label,
            credits=credits,
            rule_type=rule_type,
            rule_value=rule_value,
            source_text=source_text,
            courses=courses,
            requirement_area=COMPLEMENTARY_STUDIES_REQUIREMENT_AREA,
            option_id=None,
            option_name=None,
            option_name_raw=None,
            theme=theme,
            is_recommended=False
        )

    def _make_complementary_group_id(
        self,
        program: str,
        calendar_year: str,
        program_type: str,
        counter: int
    ) -> str:
        group_id = (
            f"{program}_{calendar_year}_{program_type}_"
            f"COMPLEMENTARY_STUDIES_{counter:03d}"
        )

        return group_id.replace("-", "_").replace(" ", "_").upper()

    def _is_advising_or_non_requirement_line(self, line: str) -> bool:
        """
        Exclude advising, registration, exchange, and program-office text that
        may mention courses but should not become Complementary Studies rules.
        """
    
        lower = line.lower()
    
        blocked_phrases = [
            "advisor",
            "go abroad",
            "going abroad",
            "transfer credits",
            "graduate on time",
            "minimal delay",
            "cannot be substituted",
            "can't register",
            "can’t register",
            "force register",
            "program office",
            "contact the program office",
            "required for your program completion",
            "biology program office",
        ]
    
        return any(phrase in lower for phrase in blocked_phrases)