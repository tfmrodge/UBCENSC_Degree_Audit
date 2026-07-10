# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""
UBC Calendar parser for ENSC degree-audit rule extraction.

This parser:
- Finds Major/Honours/Minor curriculum tables.
- Parses table rows into requirement groups.
- Parses footnotes.
- Parses Areas of Concentration sections.
"""

import re
from typing import Optional

from bs4 import BeautifulSoup

from .models import (
    RequirementPackage,
    ProgramBlock,
    RequirementGroup,
    Footnote,
    Requirement,
)

AREA_OF_CONCENTRATION_REQUIREMENT_AREA = 'Area of Concentration'

PROGRAM_HEADING_PATTERN = re.compile(
    r"^(Major|Honours|Minor)\s*\(([^)]+)\):\s*(.+)$",
    re.IGNORECASE
)

COURSE_TOKEN_PATTERN = re.compile(
    r"([A-Z]{2,5})_?V?\s*(\d{3}[A-Z]?)|(\b\d{3}[A-Z]?\b)"
)

YEAR_LABELS = {
    "First Year",
    "Second Year",
    "Third Year",
    "Fourth Year",
    "Third and Fourth Years",
}

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
}

OPTION_NAME_ALIASES = {
    "Land, Air, and Water": "LAND_AIR_WATER",
    "Land Air Water": "LAND_AIR_WATER",

    "Ecology and Conservation": "ECOLOGY_CONSERVATION",

    "Sustainability Science": "SUSTAINABILITY_SCIENCE",
    "Energy Transitions and Sustainability": "ENERGY_TRANSITIONS_SUSTAINABILITY",

    "Environment Analytics": "ENVIRONMENTAL_ANALYTICS",
    "Environmental Analytics": "ENVIRONMENTAL_ANALYTICS",

    "Environment Impacts on Human Health": "ENVIRONMENTAL_IMPACTS_HUMAN_HEALTH",
    "Environmental Impacts on Human Health": "ENVIRONMENTAL_IMPACTS_HUMAN_HEALTH",
}


class CalendarParser:
    """
    Parses a UBC Calendar HTML page into a RequirementPackage.
    """

    def parse(
        self,
        html: str,
        calendar_year: str = "2026-2027",
        program: str = "ENSC"
    ) -> RequirementPackage:
        soup = BeautifulSoup(html, "html.parser")

        package = RequirementPackage(
            program=program,
            calendar_year=calendar_year
        )

        # 1. Parse Major/Honours/Minor curriculum tables
        program_headings = self._find_program_headings(soup)

        for heading in program_headings:
            block = self._make_program_block(
                heading=heading,
                program=program,
                calendar_year=calendar_year
            )

            if block is None:
                continue

            table = heading.find_next("table")

            if table is None:
                continue

            package.program_blocks.append(block)
            
            groups, footnotes = self._parse_curriculum_table(
                table=table,
                program=program,
                calendar_year=calendar_year,
                program_type=block.program_type
            )
            
            groups = self._process_footnotes_for_requirement_groups(
                groups=groups,
                footnotes=footnotes,
                program=program,
                calendar_year=calendar_year,
                program_type=block.program_type
            )
            
            package.requirement_groups.extend(groups)
            package.footnotes.extend(footnotes)

        # 2. Parse Areas of Concentration
        aoc_groups = self._parse_option_sections(
            soup=soup,
            program=program,
            calendar_year=calendar_year
        )

        package.requirement_groups.extend(aoc_groups)

        # 3. Build legacy/simple requirements list for compatibility
        for group in package.requirement_groups:
            package.requirements.append(
                Requirement(
                    id=group.group_id,
                    name=group.label,
                    courses=group.courses
                )
            )

        return package

    # ------------------------------------------------------------------
    # Program table parsing
    # ------------------------------------------------------------------

    def _find_program_headings(self, soup):
        headings = soup.find_all(["h2", "h3", "h4", "h5", "h6"])

        program_headings = []

        for heading in headings:
            text = heading.get_text(" ", strip=True)

            if PROGRAM_HEADING_PATTERN.match(text):
                program_headings.append(heading)

        return program_headings

    def _make_program_block(
        self,
        heading,
        program: str,
        calendar_year: str
    ) -> Optional:
        heading_text = heading.get_text(" ", strip=True)

        match = PROGRAM_HEADING_PATTERN.match(heading_text)

        if not match:
            return None

        program_type = match.group(1).title()
        specialization_code = match.group(2).strip()
        title = match.group(3).strip()

        return ProgramBlock(
            program=program,
            calendar_year=calendar_year,
            program_type=program_type,
            specialization_code=specialization_code,
            title=title,
            heading_text=heading_text
        )

    def _parse_curriculum_table(
        self,
        table,
        program: str,
        calendar_year: str,
        program_type: str
    ) -> tuple[list[RequirementGroup], list[Footnote]]:
        requirement_groups = []
        footnotes = []

        current_year = None
        group_counter = 1
        footnote_counter = 1

        rows = table.find_all("tr")

        for row in rows:
            cells = row.find_all(["td", "th"])

            if not cells:
                continue

            cell_texts = [
                self._clean_cell_text(cell)
                for cell in cells
            ]

            first_cell = cell_texts[0] if len(cell_texts) > 0 else ""
            second_cell = cell_texts[1] if len(cell_texts) > 1 else ""

            if not first_cell and not second_cell:
                continue

            if first_cell in YEAR_LABELS:
                current_year = first_cell
                continue

            if self._is_footnote_row(cells, first_cell, second_cell):
                footnote = self._parse_footnote_row(
                    first_cell=first_cell,
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type,
                    footnote_counter=footnote_counter
                )

                footnotes.append(footnote)
                footnote_counter += 1
                continue

            if first_cell.lower() == "total credits":
                group_id = self._make_group_id(
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type,
                    counter=group_counter,
                    suffix="TOTAL"
                )

                requirement_groups.append(
                    RequirementGroup(
                        group_id=group_id,
                        program=program,
                        calendar_year=calendar_year,
                        program_type=program_type,
                        year_level=current_year,
                        label=first_cell,
                        credits=self._parse_credits(second_cell),
                        rule_type="year_total_credits",
                        rule_value=None,
                        source_text=first_cell,
                        courses=[],
                        requirement_area="Credit Total"
                    )
                )

                group_counter += 1
                continue

            if "minimum credits for degree" in first_cell.lower():
                group_id = self._make_group_id(
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type,
                    counter=group_counter,
                    suffix="MIN_DEGREE"
                )

                requirement_groups.append(
                    RequirementGroup(
                        group_id=group_id,
                        program=program,
                        calendar_year=calendar_year,
                        program_type=program_type,
                        year_level=None,
                        label=first_cell,
                        credits=self._parse_credits(second_cell),
                        rule_type="minimum_degree_credits",
                        rule_value=None,
                        source_text=first_cell,
                        courses=[],
                        requirement_area="Degree Minimum",
                    )
                )

                group_counter += 1
                continue

            courses = self._extract_courses_with_continuations(first_cell)
            rule_type, rule_value = self._infer_rule_type(first_cell, courses)
            
            rule_metadata = self._extract_level_requirement_metadata(
                label=first_cell,
                rule_type=rule_type,
                rule_value=rule_value
            )
            
            rule_value = rule_metadata["rule_value"]

            group_id = self._make_group_id(
                program=program,
                calendar_year=calendar_year,
                program_type=program_type,
                counter=group_counter
            )

            requirement_groups.append(
                RequirementGroup(
                    group_id=group_id,
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type,
                    year_level=current_year,
                    label=first_cell,
                    credits=self._parse_credits(second_cell),
                    rule_type=rule_type,
                    rule_value=rule_value,
                    source_text=first_cell,
                    courses=courses,
                    requirement_area=self._infer_requirement_area_from_label(first_cell),
                    rule_subject=rule_metadata["rule_subject"],
                    include_pattern=rule_metadata["include_pattern"],
                    exclude_pattern=rule_metadata["exclude_pattern"],
                    rule_unit=rule_metadata["rule_unit"]

                )
            )

            group_counter += 1

        return requirement_groups, footnotes

    # ------------------------------------------------------------------
    # Area of Concentration parsing
    # ------------------------------------------------------------------

    def _parse_option_sections(
        self,
        soup,
        program: str,
        calendar_year: str
    ) -> list:
        """
        Parse Major and Honours Area of Concentration sections.

        Uses document-order traversal rather than direct sibling traversal
        because UBC Calendar pages may not place h4 AoC headings as direct
        siblings of the h3 parent heading.
        """

        groups = []

        parent_headings = soup.find_all(["h3", "h4"])

        for parent_heading in parent_headings:
            parent_text = parent_heading.get_text(" ", strip=True)

            if not self._is_option_parent_heading(parent_text):
                continue

            program_type = self._infer_program_type_from_aoc_heading(
                parent_text
            )

            intro_text = self._collect_until_next_option_heading_or_section(
                parent_heading
            )

            minimum_credits_group = self._parse_option_minimum_credits_text(
                text=intro_text,
                program=program,
                calendar_year=calendar_year,
                program_type=program_type
            )

            if minimum_credits_group is not None:
                groups.append(minimum_credits_group)

            for element in parent_heading.find_all_next(["h3", "h4"]):
                if element == parent_heading:
                    continue

                element_text = element.get_text(" ", strip=True)

                # Stop when we reach the next h3 section
                if element.name == "h3":
                    break

                if element.name == "h4" and self._is_single_option_heading(element_text):
                    section_groups = self._parse_single_aoc_section(
                        heading=element,
                        program=program,
                        calendar_year=calendar_year,
                        program_type=program_type
                    )

                    groups.extend(section_groups)

        return groups

    def _infer_program_type_from_aoc_heading(self, heading_text: str) -> str:
        lower = heading_text.lower()

        if "honours" in lower:
            return "Honours"

        if "major" in lower or "majors" in lower:
            return "Major"

        return "Unknown"

    def _parse_single_aoc_section(
        self,
        heading,
        program: str,
        calendar_year: str,
        program_type: str
    ) -> list:
        groups = []

        option_id, option_name, option_name_raw = (
            self._parse_option_heading(
                heading.get_text(" ", strip=True)
            )
        )

        elements = self._collect_section_elements(
            heading=heading,
            stop_heading_names=["h3", "h4"]
        )

        current_context = "required"
        group_counter = 1

        for element in elements:
            if element.name == "p":
                text = element.get_text(" ", strip=True)

                if not text:
                    continue

                lower = text.lower()

                if "additional recommended courses" in lower:
                    current_context = "recommended"
                    continue

                if "additional courses for" in lower:
                    current_context = "recommended"
                    continue

                if "students should be aware" in lower:
                    continue

                if "credit exclusion" in lower:
                    continue

                category_minimum_group = self._parse_theme_minimum_rule(
                    text=text,
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type,
                    option_id=option_id,
                    option_name=option_name,
                    option_name_raw=option_name_raw,
                    group_counter=group_counter,
                    
                )

                if category_minimum_group is not None:
                    groups.append(category_minimum_group)
                    group_counter += 1

                paragraph_groups = self._parse_option_text_rule(
                    text=text,
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type,
                    option_id=option_id,
                    option_name=option_name,
                    option_name_raw=option_name_raw,
                    group_counter_start=group_counter,
                    is_recommended=(current_context == "recommended")
                )

                groups.extend(paragraph_groups)
                group_counter += len(paragraph_groups)

            elif element.name in ["ul", "ol"]:
                list_groups = self._parse_option_list(
                    list_element=element,
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type,
                    option_id=option_id,
                    option_name=option_name,
                    option_name_raw=option_name_raw,
                    group_counter_start=group_counter,
                    is_recommended=(current_context == "recommended")
                )

                groups.extend(list_groups)
                group_counter += len(list_groups)

        return groups

    def _parse_option_heading(self, text: str) -> tuple[str, str, str]:
        option_name_raw = text.strip()

        option_name = (
            option_name_raw
            .replace("Area of Concentration", "")
            .strip(" :-")
        )

        display_replacements = {
            "Environment Analytics": "Environmental Analytics",
            "Environment Impacts on Human Health": "Environmental Impacts on Human Health",
        }

        option_name = display_replacements.get(
            option_name,
            option_name
        )

        option_id = OPTION_NAME_ALIASES.get(option_name)

        if option_id is None:
            option_id = re.sub(
                r"[^A-Za-z0-9]+",
                "_",
                option_name
            ).strip("_").upper()

        return option_id, option_name, option_name_raw

    def _parse_option_minimum_credits_text(
        self,
        text: str,
        program: str,
        calendar_year: str,
        program_type: str
    ) -> Optional:
        match = re.search(
            r"minimum of\s+(\d+)\s+credits",
            text,
            re.IGNORECASE
        )

        if not match:
            return None

        credits = float(match.group(1))

        group_id = (
            f"{program}_{calendar_year}_{program_type}_AOC_MINIMUM_CREDITS"
        ).replace("-", "_").replace(" ", "_").upper()

        return RequirementGroup(
            group_id=group_id,
            program=program,
            calendar_year=calendar_year,
            program_type=program_type,
            year_level=None,
            label="Area of Concentration minimum credits",
            credits=credits,
            rule_type="option_minimum_credits",
            rule_value=None,
            source_text=text,
            courses=[],
            requirement_area=AREA_OF_CONCENTRATION_REQUIREMENT_AREA,
            option_id=None,
            option_name=None,
            option_name_raw=None,
            theme=None,
            is_recommended=False
        )

    def _parse_theme_minimum_rule(
        self,
        text: str,
        program: str,
        calendar_year: str,
        program_type: str,
        option_id: str,
        option_name: str,
        option_name_raw: str,
        group_counter: int
    ) -> Optional:
        lower = text.lower()

        rule_value = None

        if "at least three of the four" in lower:
            rule_value = 3

        elif "each of the four" in lower:
            rule_value = 4

        if rule_value is None:
            return None

        group_id = self._make_option_group_id(
            program=program,
            calendar_year=calendar_year,
            program_type=program_type,
            option_id=option_id,
            counter=group_counter
        )

        return RequirementGroup(
            group_id=group_id,
            program=program,
            calendar_year=calendar_year,
            program_type=program_type,
            year_level=None,
            label="Area of Concentration category minimum",
            credits=None,
            rule_type="theme_minimum",
            rule_value=rule_value,
            source_text=text,
            courses=[],
            requirement_area=AREA_OF_CONCENTRATION_REQUIREMENT_AREA,
            option_id=option_id,
            option_name=option_name,
            option_name_raw=option_name_raw,
            theme=None,
            is_recommended=False
        )

    def _parse_option_text_rule(
        self,
        text: str,
        program: str,
        calendar_year: str,
        program_type: str,
        option_id: str,
        option_name: str,
        option_name_raw: str,
        group_counter_start: int,
        is_recommended: bool
    ) -> list:
        groups = []

        if "must include" not in text.lower():
            return groups

        clauses = self._extract_choose_clauses(text)

        counter = group_counter_start

        for clause_text, choose_n in clauses:
            courses = self._extract_courses_with_continuations(clause_text)

            if not courses:
                continue

            group_id = self._make_option_group_id(
                program=program,
                calendar_year=calendar_year,
                program_type=program_type,
                option_id=option_id,
                counter=counter
            )

            groups.append(
                RequirementGroup(
                    group_id=group_id,
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type,
                    year_level=None,
                    label=clause_text,
                    credits=None,
                    rule_type="choose_n",
                    rule_value=choose_n,
                    source_text=text,
                    courses=courses,
                    requirement_area=AREA_OF_CONCENTRATION_REQUIREMENT_AREA,
                    option_id=option_id,
                    option_name=option_name,
                    option_name_raw=option_name_raw,
                    theme=None,
                    is_recommended=is_recommended
                )
            )

            counter += 1

        return groups

    def _parse_option_list(
        self,
        list_element,
        program: str,
        calendar_year: str,
        program_type: str,
        option_id: str,
        option_name: str,
        option_name_raw: str,
        group_counter_start: int,
        is_recommended: bool
    ) -> list:
        groups = []
        counter = group_counter_start

        for li in list_element.find_all("li", recursive=False):
            text = li.get_text(" ", strip=True)

            if not text:
                continue

            category = None
            strong = li.find("strong")

            courses = self._extract_courses_with_continuations(text)

            if not courses:
                continue

            if strong:
                category = strong.get_text(" ", strip=True).strip(":")
                rule_type = "choose_n"
                rule_value = 1
                label = text

            elif is_recommended:
                rule_type = "recommended_course_list"
                rule_value = None
                label = text

            else:
                choose_n = self._choose_n_from_text(text)

                if choose_n is not None and len(courses) > 1:
                    rule_type = "choose_n"
                    rule_value = choose_n

                elif len(courses) == 1:
                    rule_type = "required_course"
                    rule_value = None

                else:
                    rule_type = "course_list_review"
                    rule_value = None

                label = text

            group_id = self._make_option_group_id(
                program=program,
                calendar_year=calendar_year,
                program_type=program_type,
                option_id=option_id,
                counter=counter
            )

            groups.append(
                RequirementGroup(
                    group_id=group_id,
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type,
                    year_level=None,
                    label=label,
                    credits=None,
                    rule_type=rule_type,
                    rule_value=rule_value,
                    source_text=text,
                    courses=courses,
                    requirement_area=AREA_OF_CONCENTRATION_REQUIREMENT_AREA,
                    option_id=option_id,
                    option_name=option_name,
                    option_name_raw=option_name_raw,
                    theme=category,
                    is_recommended=is_recommended
                )
            )

            counter += 1

        return groups

    def _extract_choose_clauses(self, text: str) -> list[tuple[str, int]]:
        clauses = []

        pattern = re.compile(
            r"((?:at least\s+)?(?:one|two|three|four|five|six)\s+of\s+.*?)(?=(?:\s+and\s+(?:at least\s+)?(?:one|two|three|four|five|six)\s+of)|\.|$)",
            re.IGNORECASE
        )

        for match in pattern.finditer(text):
            clause_text = match.group(1).strip()
            choose_n = self._choose_n_from_text(clause_text)

            if choose_n is not None:
                clauses.append((clause_text, choose_n))

        return clauses

    def _choose_n_from_text(self, text: str) -> Optional:
        lower = text.lower()

        for word, value in NUMBER_WORDS.items():
            if re.search(rf"\bat least\s+{word}\s+of\b", lower):
                return value

            if re.search(rf"\b{word}\s+of\b", lower):
                return value

        return None

    # ------------------------------------------------------------------
    # Shared helper methods
    # ------------------------------------------------------------------

    def _collect_section_elements(
        self,
        heading,
        stop_heading_names: list[str]
    ) -> list:
        """
        Collect p/ul/ol/table elements after a heading until the next h3/h4.

        Uses document-order traversal rather than direct sibling traversal.
        """

        elements = []

        for element in heading.find_all_next(["p", "ul", "ol", "table", "h3", "h4"]):
            if element == heading:
                continue

            if element.name in stop_heading_names:
                break

            if element.name == "p" and element.find_parent(["ul", "ol"]):
                continue

            if element.name in ["p", "ul", "ol", "table"]:
                elements.append(element)

        return elements

    def _collect_until_next_option_heading_or_section(self, heading) -> str:
        """
        Collect intro text after an AoC parent heading until the first h4 AoC section
        or next h3.
        """

        chunks = []

        for element in heading.find_all_next(["p", "ul", "ol", "h3", "h4"]):
            if element == heading:
                continue

            if element.name in ["h3", "h4"]:
                break

            text = element.get_text(" ", strip=True)

            if text:
                chunks.append(text)

        return " ".join(chunks)

    def _clean_cell_text(self, cell) -> str:
        return cell.get_text(" ", strip=True)

    def _parse_credits(self, text: str) -> Optional:
        text = text.strip()

        if not text:
            return None

        try:
            return float(text)
        except ValueError:
            return None

    def _is_footnote_row(self, cells, first_cell: str, second_cell: str) -> bool:
        if len(cells) == 1:
            return True

        if cells[0].get("colspan") == "2":
            return True

        if second_cell.strip() == "" and re.match(r"^\d+\s+", first_cell):
            return True

        return False

    def _parse_footnote_row(
        self,
        first_cell: str,
        program: str,
        calendar_year: str,
        program_type: str,
        footnote_counter: int
    ) -> Footnote:
        match = re.match(r"^(\d+)\s+(.*)$", first_cell)

        if match:
            footnote_number = match.group(1)
            text = match.group(2)
        else:
            footnote_number = ""
            text = first_cell

        courses = self._extract_courses_with_continuations(text)

        footnote_id = (
            f"{program}_{calendar_year}_{program_type}_FOOTNOTE_{footnote_counter:03d}"
        ).replace("-", "_").replace(" ", "_").upper()

        return Footnote(
            footnote_id=footnote_id,
            program=program,
            calendar_year=calendar_year,
            program_type=program_type,
            footnote_number=footnote_number,
            text=text,
            courses=courses
        )

    def _extract_courses_with_continuations(self, text: str) -> list:
        """
        Extract course codes from strings like:

        ENVR_V 200, 205, 240
        CHEM_V 121 (or 111 or 141)
        GEOS_V (or GEOB_V) 206, 405, 406
        """

        if re.search(
            r"[A-Z]{2,5}_?V?\s*\d{3}\s*-\s*level",
            text,
            re.IGNORECASE
        ):
            return []

        courses = []

        # Handle alias pattern, e.g.
        # GEOS_V (or GEOB_V) 206, 405, 406
        alias_pattern = re.compile(
            r"([A-Z]{2,5})_?V?\s*\(or\s+([A-Z]{2,5})_?V?\)\s*((?:\d{3}[A-Z]?\s*(?:,|or|and)?\s*)+)",
            re.IGNORECASE
        )

        alias_spans = []

        for alias_match in alias_pattern.finditer(text):
            subject_a = alias_match.group(1).upper()
            subject_b = alias_match.group(2).upper()
            numbers_text = alias_match.group(3)

            numbers = re.findall(
                r"\b\d{3}[A-Z]?\b",
                numbers_text
            )

            for number in numbers:
                courses.append(self._normalize_course(subject_a, number))
                courses.append(self._normalize_course(subject_b, number))

            alias_spans.append(alias_match.span())

        cleaned_text_parts = []
        last_end = 0

        for start, end in alias_spans:
            cleaned_text_parts.append(text[last_end:start])
            last_end = end

        cleaned_text_parts.append(text[last_end:])
        cleaned_text = " ".join(cleaned_text_parts)

        last_subject = None

        for match in COURSE_TOKEN_PATTERN.finditer(cleaned_text):
            subject = match.group(1)
            number = match.group(2)
            continuation_number = match.group(3)

            if subject and number:
                last_subject = subject.upper()
                courses.append(
                    self._normalize_course(last_subject, number)
                )

            elif continuation_number and last_subject:
                courses.append(
                    self._normalize_course(last_subject, continuation_number)
                )

        return sorted(set(courses))

    def _normalize_course(self, subject: str, number: str) -> str:
        return f"{subject.upper()}{number.upper()}"

    def _infer_rule_type(
        self,
        label: str,
        courses: list[str]
    ) -> tuple[str, Optional[int]]:
        lower = label.lower()

        if "total credits" in lower:
            return "total_credits", None

        if "minimum credits for degree" in lower:
            return "minimum_degree_credits", None

        if re.search(r"\b\d00-level\b", lower):
            choose_n = self._choose_n_from_text(label)
        
            if choose_n is None:
                leading_number_word = re.match(
                    r"^\s*(one|two|three|four|five|six)\b",
                    lower
                )
        
                if leading_number_word:
                    choose_n = NUMBER_WORDS.get(
                        leading_number_word.group(1),
                        None
                    )
        
            return "level_requirement", choose_n

        if "electives" in lower and len(courses) == 0:
            return "elective_credits", None

        if "area of concentration" in lower:
            return "area_of_concentration_credits", None

        if "complementary studies" in lower:
            return "complementary_studies_credits", None

        
        normalized = lower.replace("'", "").replace("’", "")
        
        if "tools elective" in normalized or "tools electives" in normalized:
            return "referenced_footnote_rule", None


        if lower.startswith("one of"):
            return "choose_n", 1

        if " or " in lower and len(courses) > 1:
            return "choose_n", 1

        choose_n = self._choose_n_from_text(label)

        if choose_n is not None and len(courses) > 1:
            return "choose_n", choose_n

        if len(courses) == 1:
            return "required_course", None

        if len(courses) > 1:
            return "required_all", None

        return "unknown", None

    def _extract_level_requirement_metadata(
        self,
        label: str,
        rule_type: str,
        rule_value
    ) -> dict:
        """
        Extract structured metadata for level requirements.
    
        Examples:
        - PHYS_V 100-level
          -> rule_subject PHYS, include_pattern 100-level, rule_unit credits
    
        - One 200-level BIOL_V OR CHEM_V
          -> rule_subject BIOL;CHEM, include_pattern 200-level,
             rule_value 1, rule_unit course
        """
    
        metadata = {
            "rule_subject": None,
            "include_pattern": None,
            "exclude_pattern": None,
            "rule_unit": None,
            "rule_value": rule_value,
        }
    
        if rule_type != "level_requirement":
            return metadata
    
        text = str(label).strip()
    
        # Pattern 1:
        # One 200-level BIOL_V OR CHEM_V
        #
        # Important: check this BEFORE the PHYS_V 100-level pattern,
        # otherwise "One 200-level" can be incorrectly parsed as subject ONE.
        level_first = re.search(
            r"^\s*(?:(one|two|three|four|five|six)\s+)?(\d00)-level\s+(.+)$",
            text,
            re.IGNORECASE
        )
    
        if level_first:
            number_word = level_first.group(1)
            level = level_first.group(2)
            tail = level_first.group(3)
    
            subjects = re.findall(
                r"\b([A-Z]{2,5})_?V\b",
                tail,
                re.IGNORECASE
            )
            
            subjects = [
                subject.upper()
                for subject in subjects
                if subject.lower() not in NUMBER_WORDS
            ]
    
            if subjects:
                metadata["rule_subject"] = ";".join(sorted(set(subjects)))
                metadata["include_pattern"] = f"{level}-level"
                metadata["rule_unit"] = "course"
    
                if number_word:
                    metadata["rule_value"] = NUMBER_WORDS.get(
                        number_word.lower(),
                        rule_value
                    )
    
                return metadata
    
        # Pattern 2:
        # PHYS_V 100-level
        #
        # Require _V or V after the subject so that ordinary words like "One"
        # do not get treated as subjects.
        subject_before_level = re.search(
            r"\b([A-Z]{2,5})_?V\s+(\d00)-level\b",
            text,
            re.IGNORECASE
        )
    
        if subject_before_level:
            subject = subject_before_level.group(1).upper()
            level = subject_before_level.group(2)
    
            metadata["rule_subject"] = subject
            metadata["include_pattern"] = f"{level}-level"
            metadata["rule_unit"] = "credits"
    
            return metadata
    
        return metadata

    def _make_group_id(
        self,
        program: str,
        calendar_year: str,
        program_type: str,
        counter: int,
        suffix: Optional[str] = None
    ) -> str:
        base = f"{program}_{calendar_year}_{program_type}_{counter:03d}"

        if suffix:
            base = f"{base}_{suffix}"

        return base.replace("-", "_").replace(" ", "_").upper()

    def _make_option_group_id(
        self,
        program: str,
        calendar_year: str,
        program_type: str,
        option_id: str,
        counter: int
    ) -> str:
        group_id = (
            f"{program}_{calendar_year}_{program_type}_"
            f"AOC_{option_id}_{counter:03d}"
        )

        return group_id.replace("-", "_").replace(" ", "_").upper()

    def _is_option_parent_heading(self, heading_text: str) -> bool:
        lower = heading_text.lower()

        return (
            "areas of concentration" in lower
            and "required courses" in lower
        )

    def _is_single_option_heading(self, heading_text: str) -> bool:
        return "area of concentration" in heading_text.lower()

    def debug_aoc_sections(self, soup):
        """
        Optional debug helper.
        """

        parent_headings = soup.find_all(["h3", "h4"])

        for parent_heading in parent_headings:
            parent_text = parent_heading.get_text(" ", strip=True)

            if not self._is_option_parent_heading(parent_text):
                continue

            program_type = self._infer_program_type_from_aoc_heading(
                parent_text
            )

            print()
            print("AOC PARENT")
            print("----------")
            print(f"Heading: {parent_text}")
            print(f"Program type: {program_type}")

            for element in parent_heading.find_all_next(["h3", "h4"]):
                if element == parent_heading:
                    continue

                element_text = element.get_text(" ", strip=True)

                if element.name == "h3":
                    break

                if element.name == "h4" and self._is_single_option_heading(element_text):
                    print(f"  AOC SECTION: {element_text}")
    
    def _extract_trailing_footnote_number(self, text: str) -> Optional:
        """
        Extract a trailing footnote number from labels like:
        - 'Tools' Elective 11
        - Area of Concentration 12
        - Electives 6,7
    
        Returns the last number as a string.
        """
    
        matches = re.findall(r"\b(\d+)\b", text)
    
        if not matches:
            return None
    
        return matches[-1]
    
    def _link_footnotes_to_requirement_groups(
        self,
        groups: list[RequirementGroup],
        footnotes: list[Footnote]
    ) -> list:
        """
        Update existing requirement groups using matching footnotes.
    
        Example:
        Table row:
            'Tools' Elective 11
    
        Footnote:
            11 Tools Elective: One of ATSC_V 303, CHEM_V 211...
    
        Result:
            The original Tools Elective group receives the footnote courses
            and becomes rule_type = choose_n.
        """
    
        footnote_by_number = {
            footnote.footnote_number: footnote
            for footnote in footnotes
            if footnote.footnote_number
        }
    
        for group in groups:
            label_lower = group.label.lower()
            normalized_label = label_lower.replace("'", "").replace("’", "")
    
            footnote_number = self._extract_trailing_footnote_number(
                group.label
            )
    
            if footnote_number is None:
                continue
    
            footnote = footnote_by_number.get(footnote_number)
    
            if footnote is None:
                continue
    
            footnote_lower = footnote.text.lower()
            normalized_footnote = footnote_lower.replace("'", "").replace("’", "")
    
            # Link Tools Elective rows to Tools Elective footnotes
            if (
                "tools elective" in normalized_label
                or "tools electives" in normalized_label
            ) and (
                "tools elective" in normalized_footnote
                or "tools electives" in normalized_footnote
            ):
                group.courses = footnote.courses
    
                choose_n = self._choose_n_from_text(footnote.text)
    
                if choose_n is None:
                    # Infer from table credits if footnote wording is unclear.
                    if group.credits is not None and group.credits >= 6:
                        choose_n = 2
                    else:
                        choose_n = 1
    
                group.rule_type = "choose_n"
                group.rule_value = choose_n
    
                group.source_text = (
                    f"{group.source_text} | Footnote {footnote.footnote_number}: "
                    f"{footnote.text}"
                )
            # Link level-requirement exclusions from footnotes.
            if group.rule_type == "level_requirement":
                excluded_courses = self._extract_excluded_courses_from_footnote(
                    footnote.text
                )
            
                if excluded_courses:
                    group.exclude_pattern = ";".join(excluded_courses)
            
                    group.source_text = (
                        f"{group.source_text} | Footnote {footnote.footnote_number}: "
                        f"{footnote.text}"
                    )

            # You can add future linkers here:
            # - Complementary Studies
            # - Communication Requirement
            # - Area of Concentration notes
    
        return groups
    
    def _extract_excluded_courses_from_footnote(self, text: str) -> list:
        """
        Extract excluded courses from footnote text.
    
        Example:
        excluding PHYS_V 100 and PHYS_V 170
        -> PHYS100; PHYS170
        """
    
        match = re.search(
            r"excluding\s+(.+?)(?:\.|;|$)",
            text,
            re.IGNORECASE
        )
    
        if not match:
            return []
    
        exclusion_text = match.group(1)
    
        return self._extract_courses_with_continuations(exclusion_text)
    
    def _infer_requirement_area_from_label(self, label: str) -> str:
        lower = label.lower()
        normalized = lower.replace("'", "").replace("’", "")
    
        if "area of concentration" in lower:
            return "Area of Concentration"
    
        if "complementary studies" in lower:
            return "Complementary Studies"
    
        if "tools elective" in normalized or "tools electives" in normalized:
            return "Tools Elective"
    
        if "communication requirement" in lower:
            return "Communication Requirement"
    
        if "elective" in lower:
            return "Electives"
    
        if "total credits" in lower:
            return "Credit Total"
    
        if "minimum credits for degree" in lower:
            return "Degree Minimum"
    
        return "Core Requirement"
    
    def _parse_aoc_minimum_credit_footnote(
        self,
        footnote: Footnote,
        program: str,
        calendar_year: str,
        program_type: str
    ) -> list:
        """
        Parse option-specific Area of Concentration minimum-credit footnotes.
    
        Example:
        Students must take a minimum of 21 credits for Energy Transitions and
        Sustainability, Environmental Analytics, and Ecology and Conservation.
        Students must take a minimum of 22 credits for Land Air Water and
        Environmental Impacts on Human Health.
        """
    
        text = footnote.text
    
        if "minimum of" not in text.lower():
            return []
    
        if "credits" not in text.lower():
            return []
    
        if "area" not in text.lower() and "energy transitions" not in text.lower():
            # Conservative guard so we do not accidentally parse unrelated footnotes.
            return []
    
        groups = []
    
        option_credit_rules = [
            {
                "credits": 21,
                "names": [
                    "Energy Transitions and Sustainability",
                    "Environmental Analytics",
                    "Ecology and Conservation",
                ],
            },
            {
                "credits": 22,
                "names": [
                    "Land Air Water",
                    "Land, Air, and Water",
                    "Environmental Impacts on Human Health",
                    "Environment Impacts on Human Health",
                ],
            },
        ]
    
        counter = 1
    
        for rule in option_credit_rules:
            credits = float(rule["credits"])
    
            for option_name_text in rule["names"]:
                option_id, option_name, option_name_raw = self._parse_option_heading(
                    f"{option_name_text} Area of Concentration"
                )
    
                # Only create the group if the option name appears in the footnote text.
                normalized_text = text.lower().replace(",", "")
                normalized_option = option_name_text.lower().replace(",", "")
    
                if normalized_option not in normalized_text:
                    continue
    
                group_id = (
                    f"{program}_{calendar_year}_{program_type}_"
                    f"AOC_{option_id}_MINIMUM_CREDITS"
                ).replace("-", "_").replace(" ", "_").upper()
    
                groups.append(
                    RequirementGroup(
                        group_id=group_id,
                        program=program,
                        calendar_year=calendar_year,
                        program_type=program_type,
                        year_level=None,
                        label=f"{option_name} Area of Concentration minimum credits",
                        credits=credits,
                        rule_type="option_minimum_credits",
                        rule_value=None,
                        source_text=f"Footnote {footnote.footnote_number}: {text}",
                        courses=[],
                        requirement_area=AREA_OF_CONCENTRATION_REQUIREMENT_AREA,
                        option_id=option_id,
                        option_name=option_name,
                        option_name_raw=option_name_raw,
                        theme=None,
                        rule_unit="credits",
                        is_recommended=False
                    )
                )
    
                counter += 1
    
        return groups
    
    def _convert_footnotes_to_non_course_requirement_groups(
        self,
        footnotes: list[Footnote],
        program: str,
        calendar_year: str,
        program_type: str
    ) -> list:
        """
        Convert non-course footnote rules into RequirementGroup rows.
    
        Currently handles:
        - option-specific Area of Concentration minimum credits
        """
    
        groups = []
    
        for footnote in footnotes:
            groups.extend(
                self._parse_aoc_minimum_credit_footnote(
                    footnote=footnote,
                    program=program,
                    calendar_year=calendar_year,
                    program_type=program_type
                )
            )
    
        return groups

    def _process_footnotes_for_requirement_groups(
        self,
        groups: list[RequirementGroup],
        footnotes: list[Footnote],
        program: str,
        calendar_year: str,
        program_type: str
    ) -> list:
        """
        Process footnotes that affect requirement groups.
    
        This does two things:
        1. Updates existing groups using footnotes.
           Example: Tools Elective row receives eligible courses from a footnote.
    
        2. Creates new requirement groups from non-course footnote rules.
           Example: Area of Concentration option-specific minimum credits.
        """
    
        updated_groups = self._link_footnotes_to_requirement_groups(
            groups=groups,
            footnotes=footnotes
        )
    
        new_groups = self._convert_footnotes_to_non_course_requirement_groups(
            footnotes=footnotes,
            program=program,
            calendar_year=calendar_year,
            program_type=program_type
        )
    
        updated_groups.extend(new_groups)
    
        return updated_groups