# -*- coding: utf-8 -*-
"""
Created on Wed Jul  8 13:44:09 2026
Tim Rodgers with M365 CoPilot

Specialization auditor for the degree audit pipeline.

Checks program/specialization requirements from:
- requirement_groups.csv
- requirement_courses.csv

This first version performs non-exclusive requirement matching.
This checks "Does this course match a specification"
allocation_engine.py will handle exclusive course assignments
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .specialization_requirement_resolver import SpecializationRequirementResolver
from .models import AllocationConfig

import pandas as pd


class SpecializationAuditor:
    """
    Audits specialization requirements using classified course data.
    """

    def __init__(
        self,
        requirement_groups: pd.DataFrame,
        requirement_courses: pd.DataFrame,
        profile,
        options,
        allocation_config: AllocationConfig | None = None,
    ):
        self.profile = profile
        self.options = options
    
        self.resolver = SpecializationRequirementResolver(
            requirement_groups=requirement_groups,
            requirement_courses=requirement_courses,
            profile=profile,
            allocation_config=allocation_config,
        )
    
        self.requirement_groups = self.resolver.requirement_groups
        self.requirement_courses = self.resolver.requirement_courses

    @classmethod
    def from_audit_bundle(cls, bundle):
        allocation_config_df = (
            bundle.specialization_requirements.allocation_config
        )
    
        if allocation_config_df is not None:
            allocation_config = AllocationConfig.from_dataframe(
                allocation_config_df
            )
        else:
            allocation_config = AllocationConfig()
    
        return cls(
            requirement_groups=bundle.specialization_requirements.requirement_groups,
            requirement_courses=bundle.specialization_requirements.requirement_courses,
            profile=bundle.profile,
            options=bundle.options,
            allocation_config=allocation_config,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def audit(
        self,
        classified_courses: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Run specialization audit.

        Returns
        -------
        pd.DataFrame
            One row per audited specialization requirement.
        """

        counted_courses = self._filter_counted_courses(
            classified_courses
        )
        
        applicable_groups = self.resolver.get_applicable_requirement_groups()
        
        rows = []
        
        canonical_aoc_row = self._audit_canonical_aoc_minimum(
            courses=counted_courses,
            applicable_groups=applicable_groups
        )
        
        if canonical_aoc_row is not None:
            rows.append(canonical_aoc_row)
        
        canonical_tools_row = self._audit_canonical_tools_elective(
            courses=counted_courses,
            applicable_groups=applicable_groups
        )
        
        if canonical_tools_row is not None:
            rows.append(canonical_tools_row)

        for _, group in applicable_groups.iterrows():
            rule_type = str(group.get("rule_type", "")).strip()

            if self._should_skip_group(group):
                continue

            if rule_type in {
                "required_course",
                "required_all",
                "choose_n",
                "referenced_footnote_rule",
            }:
                rows.append(
                    self._audit_course_group(
                        group=group,
                        courses=counted_courses
                    )
                )


            elif rule_type == "theme_minimum":
                rows.append(
                    self._audit_theme_minimum(
                        group=group,
                        courses=counted_courses
                    )
                )

            elif rule_type == "complementary_studies_credits":
                rows.append(
                    self._audit_complementary_studies_credits(
                        group=group,
                        courses=counted_courses
                    )
                )
            elif rule_type == "level_requirement":
                rows.append(
                    self._audit_level_requirement(
                        group=group,
                        courses=counted_courses
                    )
                )

            else:
                rows.append(
                    self._make_summary_row(
                        group=group,
                        status="review",
                        completed=0,
                        required=0,
                        remaining=0,
                        surplus=0,
                        unit="",
                        matched_courses="",
                        notes=(
                            f"Rule type '{rule_type}' is not yet audited "
                            "by SpecializationAuditor."
                        )
                    )
                )

        return pd.DataFrame(rows)

    def print_summary(
        self,
        specialization_audit: pd.DataFrame
    ) -> None:
        """
        Print readable terminal summary.
        """

        print()
        print("Specialization Requirement Audit")
        print("================================")

        if specialization_audit.empty:
            print("No specialization requirements audited.")
            print()
            return

        for _, row in specialization_audit.iterrows():
            group_id = row.get("group_id", "")
            area = row.get("requirement_area", "")
            status = row.get("status", "")
            completed = row.get("completed", "")
            required = row.get("required", "")
            remaining = row.get("remaining", "")
            unit = row.get("unit", "")
            label = row.get("label", "")
            notes = row.get("notes", "")

            print(
                f"{group_id}: {status} "
                f"({completed}/{required} {unit}; remaining: {remaining})"
            )
            print(f"  Area: {area}")
            print(f"  Label: {label}")

            if notes:
                print(f"  Notes: {notes}")

        print()

    def write_summary(
        self,
        specialization_audit: pd.DataFrame,
        output_dir: str | Path,
        filename: str = "specialization_audit.csv"
    ) -> Path:
        """
        Write specialization audit summary to CSV.
        """

        output_dir = Path(output_dir)

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        output_path = output_dir / filename

        specialization_audit.to_csv(
            output_path,
            index=False
        )

        return output_path

    # ------------------------------------------------------------------
    # Individual audit methods
    # ------------------------------------------------------------------

    def _audit_course_group(
        self,
        group: pd.Series,
        courses: pd.DataFrame
    ) -> dict:
        group_id = group["group_id"]
        rule_type = str(group.get("rule_type", "")).strip()
    
        eligible_courses = self.resolver.get_group_course_codes(group_id)
    
        matched = self._match_courses_to_eligible_list(
            courses=courses,
            eligible_course_codes=eligible_courses
        )
    
        matched_course_count = matched[
            "effective_course_code"
        ].drop_duplicates().shape[0]
    
        matched_credits = matched["credits"].sum()
    
        expected_credits = self._required_credits_from_group(group)
    
        if rule_type == "required_course":
            required = 1
            unit = "course"
    
        elif rule_type == "required_all":
            required = len(set(eligible_courses))
            unit = "course"
    
        elif rule_type == "choose_n":
            required = self._safe_rule_value(group, default=1)
            unit = "course"
    
        elif rule_type == "referenced_footnote_rule":
            required = self._safe_rule_value(group, default=1)
            unit = "course"
    
        else:
            required = 1
            unit = "course"
    
        completed = min(matched_course_count, required)
    
        notes = self._course_group_notes(
            group=group,
            eligible_courses=eligible_courses
        )
    
        if expected_credits > 0:
            notes = (
                f"{notes} Matched credits={matched_credits}; "
                f"expected row credits={expected_credits}."
            )
    
        return self._make_summary_row_from_values(
            group=group,
            completed=completed,
            required=required,
            unit=unit,
            matched_courses=self._course_list(matched),
            notes=notes,
            completed_credits=matched_credits,
            required_credits=expected_credits
        )

    def _get_option_eligible_course_codes(
        self,
        option_id: str
    ) -> list:
        profile_program = str(self.profile.program).strip().upper()
        profile_calendar_year = str(self.profile.calendar_year).strip()
        profile_program_type = str(self.profile.program_type).strip().upper()
    
        rows = self.requirement_courses.copy()
    
        rows["program_normalized"] = (
            rows["program"]
            .astype(str)
            .str.strip()
            .str.upper()
        )
    
        rows["calendar_year_normalized"] = (
            rows["calendar_year"]
            .astype(str)
            .str.strip()
        )
    
        rows["program_type_normalized"] = (
            rows["program_type"]
            .astype(str)
            .str.strip()
            .str.upper()
        )
    
        rows["option_id_normalized"] = (
            rows["option_id"]
            .astype(str)
            .str.strip()
            .str.upper()
        )
    
        rows = rows[
            (rows["requirement_area"] == "Area of Concentration")
            &
            (rows["option_id_normalized"] == option_id.upper())
            &
            (
                (rows["program_normalized"] == profile_program)
                | (rows["program_normalized"] == "ALL")
                | (rows["program_normalized"] == "")
            )
            &
            (
                (rows["calendar_year_normalized"] == profile_calendar_year)
                | (rows["calendar_year_normalized"] == "ALL")
                | (rows["calendar_year_normalized"] == "")
            )
            &
            (
                (rows["program_type_normalized"] == profile_program_type)
                | (rows["program_type_normalized"] == "ALL")
                | (rows["program_type_normalized"] == "")
            )
            &
            (
                rows["is_recommended"]
                .astype(str)
                .str.lower()
                != "true"
            )
        ]
    
        return (
            rows["course_code"]
            .dropna()
            .astype(str)
            .str.strip()
            .drop_duplicates()
            .tolist()
        )

    def _audit_theme_minimum(
        self,
        group: pd.Series,
        courses: pd.DataFrame
    ) -> dict:
        """
        Audit theme/category minimums within an option.

        Example:
        Land/Air/Water may require courses from at least 3 of 4 themes.
        """

        option_id = str(group.get("option_id", "")).strip()

        if not option_id:
            option_id = self.profile.option_id

        if not option_id:
            return self._make_summary_row_from_values(
                group=group,
                completed=0,
                required=self._safe_rule_value(group, default=0),
                unit="theme",
                matched_courses="",
                notes="No option_id available for theme minimum."
            )

        option_course_rows = self.requirement_courses[
            (self.requirement_courses["requirement_area"] == "Area of Concentration")
            & (self.requirement_courses["option_id"] == option_id)
            & (self.requirement_courses["theme"].astype(str).str.strip() != "")
        ].copy()

        completed_themes = []

        matched_all = []

        for theme in sorted(option_course_rows["theme"].dropna().unique()):
            theme_rows = option_course_rows[
                option_course_rows["theme"] == theme
            ]

            eligible_courses = (
                theme_rows["course_code"]
                .dropna()
                .astype(str)
                .tolist()
            )

            matched = self._match_courses_to_eligible_list(
                courses=courses,
                eligible_course_codes=eligible_courses
            )

            if not matched.empty:
                completed_themes.append(theme)
                matched_all.append(matched)

        if matched_all:
            matched_courses_df = pd.concat(
                matched_all,
                ignore_index=True
            ).drop_duplicates(
                subset=["effective_course_code"]
            )
        else:
            matched_courses_df = pd.DataFrame(columns=courses.columns)

        completed = len(completed_themes)
        required = self._safe_rule_value(group, default=0)

        return self._make_summary_row_from_values(
            group=group,
            completed=completed,
            required=required,
            unit="theme",
            matched_courses=self._course_list(matched_courses_df),
            notes=(
                "Completed themes: "
                + ";".join(completed_themes)
            )
        )

    def _audit_complementary_studies_credits(
        self,
        group: pd.Series,
        courses: pd.DataFrame
    ) -> dict:
        """
        Audit Complementary Studies credit minimum using complementary
        eligibility rules.
        """
    
        eligible_courses = self.resolver.get_complementary_studies_eligible_course_codes()
    
        source_groups = pd.DataFrame([group])
    
        return self._audit_canonical_credit_requirement(
            courses=courses,
            source_groups=source_groups,
            requirement_area="Complementary Studies",
            synthetic_label=str(group.get("label", "Complementary Studies")),
            synthetic_rule_type="complementary_studies_credits",
            synthetic_suffix=str(group.get("group_id", "COMPLEMENTARY_STUDIES")),
            required_credits=self._required_credits_from_group(group),
            eligible_courses=eligible_courses,
            notes_prefix="Credits matched against Complementary Studies eligibility rules."
        )


    def _audit_level_requirement(
        self,
        group: pd.Series,
        courses: pd.DataFrame
    ) -> dict:
        """
        Audit level-based requirements.
    
        Examples:
        - PHYS_V 100-level
          rule_subject = PHYS
          include_pattern = 100-level
          exclude_pattern = PHYS100;PHYS170
          rule_unit = credits
    
        - One 200-level BIOL_V OR CHEM_V
          rule_subject = BIOL;CHEM
          include_pattern = 200-level
          rule_value = 1
          rule_unit = course
        """
    
        rule_subjects = self.resolver.split_semicolon(
            group.get("rule_subject", "")
        )
    
        include_pattern = str(
            group.get("include_pattern", "")
        ).strip()
    
        exclude_pattern = str(
            group.get("exclude_pattern", "")
        ).strip()
    
        rule_unit = str(
            group.get("rule_unit", "")
        ).strip().lower()
    
        if not rule_subjects:
            raise ValueError(
                "level_requirement is missing rule_subject. "
                f"group_id={group.get('group_id', '')}, "
                f"label={group.get('label', '')}"
            )
    
        if not include_pattern:
            raise ValueError(
                "level_requirement is missing include_pattern. "
                f"group_id={group.get('group_id', '')}, "
                f"label={group.get('label', '')}"
            )
    
        if not rule_unit:
            raise ValueError(
                "level_requirement is missing rule_unit. "
                f"group_id={group.get('group_id', '')}, "
                f"label={group.get('label', '')}"
            )
    
        # matched = self.resolver.match_courses_to_level_requirement(
        #     courses=courses,
        #     rule_subjects=rule_subjects,
        #     include_pattern=include_pattern,
        #     exclude_pattern=exclude_pattern
        # )
        
        matched = self.resolver.match_courses_to_level_requirement(
            courses=courses,
            group_row=group,
        )
    
        matched_course_count = matched[
            "effective_course_code"
        ].drop_duplicates().shape[0]
    
        matched_credits = matched["credits"].sum()
    
        expected_credits = self._required_credits_from_group(
            group
        )
    
        if rule_unit == "course":
            required = self._safe_rule_value(
                group,
                default=1
            )
    
            # Cap displayed completion at required amount.
            # Actual matched courses/credits are still shown in notes and credit columns.
            completed = min(
                matched_course_count,
                required
            )
    
            unit = "course"
    
            notes = (
                f"Level requirement matched subjects={';'.join(rule_subjects)}; "
                f"include_pattern={include_pattern}; "
                f"exclude_pattern={exclude_pattern}; "
                f"rule_unit={rule_unit}. "
                f"Matched {matched_course_count} eligible course(s) "
                f"worth {matched_credits} credit(s)."
            )
    
        elif rule_unit == "credits":
            completed = matched_credits
            required = expected_credits
            unit = "credits"
    
            notes = (
                f"Level requirement matched subjects={';'.join(rule_subjects)}; "
                f"include_pattern={include_pattern}; "
                f"exclude_pattern={exclude_pattern}; "
                f"rule_unit={rule_unit}. "
                f"Matched {matched_course_count} eligible course(s)."
            )
    
        else:
            raise ValueError(
                "Unsupported level_requirement rule_unit. "
                f"group_id={group.get('group_id', '')}, "
                f"rule_unit={rule_unit}"
            )
    
        return self._make_summary_row_from_values(
            group=group,
            completed=completed,
            required=required,
            unit=unit,
            matched_courses=self._course_list(matched),
            notes=notes,
            completed_credits=matched_credits,
            required_credits=expected_credits
        )

    # ------------------------------------------------------------------
    # Requirement selection
    # ------------------------------------------------------------------

    def _should_skip_group(
        self,
        group: pd.Series
    ) -> bool:
        rule_type = str(group.get("rule_type", "")).strip()
        requirement_area = str(group.get("requirement_area", "")).strip()
        
        
        if requirement_area == "Tools Elective":
                return True


        skip_rule_types = {
            "complementary_studies_eligible_courses",
            "subject_all",
            "recommended_course_list",
            "year_total_credits",
            "minimum_degree_credits",
            "elective_credits",
            "area_of_concentration_credits",
            "option_minimum_credits",
        }

        if rule_type in skip_rule_types:
            return True

        if requirement_area in {
            "Credit Total",
            "Degree Minimum",
            "Faculty Requirement",
        }:
            return True

        return False

    # ------------------------------------------------------------------
    # Course matching helpers
    # ------------------------------------------------------------------

    def _match_courses_to_eligible_list(
        self,
        courses: pd.DataFrame,
        eligible_course_codes: list[str]
    ) -> pd.DataFrame:
        if not eligible_course_codes:
            return pd.DataFrame(columns=courses.columns)

        normalized_eligible = [
            str(code).strip().upper()
            for code in eligible_course_codes
            if str(code).strip()
        ]

        matched_indices = []

        for idx, row in courses.iterrows():
            student_code = str(
                row.get("effective_course_code", "")
            ).strip().upper()

            if self._course_matches_any_eligible(
                student_code=student_code,
                eligible_course_codes=normalized_eligible
            ):
                matched_indices.append(idx)

        return courses.loc[matched_indices].copy()

    @staticmethod
    def _course_matches_any_eligible(
        student_code: str,
        eligible_course_codes: list[str]
    ) -> bool:
        if not student_code:
            return False

        for eligible in eligible_course_codes:
            if not eligible:
                continue

            if eligible.endswith("*"):
                prefix = eligible.replace("*", "")
                if student_code.startswith(prefix):
                    return True

            elif student_code == eligible:
                return True

        return False
    
    @staticmethod
    def _level_bounds_from_include_pattern(
        include_pattern: str
    ) -> tuple[Optional[int], Optional[int]]:
        """
        Convert include patterns like:
        - 100-level
        - 200-level
    
        into numeric bounds:
        - 100, 199
        - 200, 299
        """
    
        import re
    
        text = str(include_pattern).strip().lower()
    
        match = re.match(
            r"^(\d)00-level$",
            text
        )
    
        if not match:
            return None, None
    
        hundreds = int(match.group(1)) * 100
    
        return hundreds, hundreds + 99

    # ------------------------------------------------------------------
    # Formatting / summary helpers
    # ------------------------------------------------------------------
    
    def _make_summary_row_from_values(
        self,
        group: pd.Series,
        completed,
        required,
        unit: str,
        matched_courses: str,
        notes: str,
        completed_credits=None,
        required_credits=None
    ) -> dict:
        completed_value = float(completed) if completed is not None else 0
        required_value = float(required) if required is not None else 0
    
        remaining_value = max(required_value - completed_value, 0)
        surplus_value = max(completed_value - required_value, 0)
    
        # If the rule itself is credit-based, use completed/required as credit fields
        # unless more specific values were passed.
        if unit == "credits":
            if completed_credits is None:
                completed_credits = completed_value
    
            if required_credits is None:
                required_credits = required_value
    
        if required_value == 0:
            status = "review"
    
        elif completed_value >= required_value:
            status = "satisfied"
    
        elif completed_value > 0:
            status = "partial"
    
        else:
            status = "missing"
    
        return self._make_summary_row(
            group=group,
            status=status,
            completed=completed_value,
            required=required_value,
            remaining=remaining_value,
            surplus=surplus_value,
            unit=unit,
            matched_courses=matched_courses,
            notes=notes,
            completed_credits=completed_credits,
            required_credits=required_credits
        )
    
    @staticmethod
    def _make_summary_row(
        group: pd.Series,
        status: str,
        completed,
        required,
        remaining,
        surplus,
        unit: str,
        matched_courses: str,
        notes: str,
        completed_credits=None,
        required_credits=None
    ) -> dict:
        return {
            "group_id": group.get("group_id", ""),
            "requirement_area": group.get("requirement_area", ""),
            "option_id": group.get("option_id", ""),
            "option_name": group.get("option_name", ""),
            "theme": group.get("theme", ""),
            "label": group.get("label", ""),
            "rule_type": group.get("rule_type", ""),
            "status": status,
            "completed": completed,
            "required": required,
            "remaining": remaining,
            "surplus": surplus,
            "unit": unit,
            "completed_credits": completed_credits,
            "required_credits": required_credits,
            "matched_courses": matched_courses,
            "notes": notes,
        }

    @staticmethod
    def _course_list(
        courses: pd.DataFrame
    ) -> str:
        if courses.empty:
            return ""

        return ";".join(
            courses["effective_course_code"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .tolist()
        )

    @staticmethod
    def _safe_rule_value(
        group: pd.Series,
        default: float = 0
    ) -> float:
        value = group.get("rule_value", default)

        if pd.isna(value) or value == "":
            return float(default)

        return float(value)

    @staticmethod
    def _required_credits_from_group(
        group: pd.Series
    ) -> float:
        value = group.get("credits", 0)

        if pd.isna(value) or value == "":
            return 0

        return float(value)

    @staticmethod
    def _course_group_notes(
        group: pd.Series,
        eligible_courses: list[str]
    ) -> str:
        if not eligible_courses:
            return "No eligible course list found for this requirement group."
    
        unique_courses = sorted(set(eligible_courses))
    
        return (
            f"Eligible courses: {len(unique_courses)} "
            f"({';'.join(unique_courses)}); "
            f"source rule type: {group.get('rule_type', '')}."
        )

    # ------------------------------------------------------------------
    # Input normalization and filtering
    # ------------------------------------------------------------------

    def _normalize_inputs(self) -> None:
        for df in [
            self.requirement_groups,
            self.requirement_courses,
        ]:
            for column in [
                "group_id",
                "program",
                "calendar_year",
                "program_type",
                "requirement_area",
                "option_id",
                "option_name",
                "theme",
                "rule_type",
                "course_code",
                "is_recommended",
                "rule_subject",
                "include_pattern",
                "exclude_pattern",
                "rule_unit",
            ]:
                if column not in df.columns:
                    df[column] = ""

        for column in ["credits", "rule_value"]:
            if column in self.requirement_groups.columns:
                self.requirement_groups[column] = pd.to_numeric(
                    self.requirement_groups[column],
                    errors="coerce"
                )

            if column in self.requirement_courses.columns:
                self.requirement_courses[column] = pd.to_numeric(
                    self.requirement_courses[column],
                    errors="coerce"
                )

    def _filter_counted_courses(
        self,
        courses: pd.DataFrame
    ) -> pd.DataFrame:
        df = courses.copy()

        count_statuses = [
            status.strip().lower()
            for status in self.options.count_statuses
        ]

        excluded_statuses = {
            "failed",
            "withdrawn",
            "w",
            "fail",
        }

        df["status"] = df["status"].astype(str).str.lower().str.strip()

        df = df[
            df["status"].isin(count_statuses)
            & ~df["status"].isin(excluded_statuses)
        ].copy()

        return df

    def _audit_canonical_aoc_minimum(
        self,
        courses: pd.DataFrame,
        applicable_groups: pd.DataFrame
    ) -> Optional:
        resolved = self._resolve_canonical_aoc_credit_requirement(
            applicable_groups=applicable_groups
        )
    
        if resolved is None:
            return None
    
        required_credits = resolved["required_credits"]
        source = resolved["source"]
    
        option_id = str(self.profile.option_id or "").strip()
        option_name = self._get_selected_option_name(applicable_groups)
    
        if not option_id:
            synthetic_group = self._make_synthetic_group(
                requirement_area="Area of Concentration",
                label="Area of Concentration total credits",
                rule_type="option_total_credits",
                suffix="AOC_NO_OPTION_CANONICAL_TOTAL_CREDITS",
                option_id="",
                option_name="",
            )
    
            return self._make_summary_row_from_values(
                group=synthetic_group,
                completed=0,
                required=required_credits,
                unit="credits",
                matched_courses="",
                notes=(
                    "No option_id selected in student_profile.csv. "
                    f"Canonical AoC source: {source}."
                )
            )
    
        eligible_courses = self.resolver.get_option_eligible_course_codes(
            option_id=option_id
        )
    
        source_groups = resolved["source_groups"]
    
        return self._audit_canonical_credit_requirement(
            courses=courses,
            source_groups=source_groups,
            requirement_area="Area of Concentration",
            synthetic_label="Area of Concentration total credits",
            synthetic_rule_type="option_total_credits",
            synthetic_suffix=f"AOC_{option_id}_CANONICAL_TOTAL_CREDITS",
            required_credits=required_credits,
            eligible_courses=eligible_courses,
            option_id=option_id,
            option_name=option_name,
            notes_prefix=f"Canonical AoC source: {source}."
        )
    
    
    def _resolve_canonical_aoc_credit_requirement(
        self,
        applicable_groups: pd.DataFrame
    ) -> Optional:
        """
        Resolve the canonical Area of Concentration credit requirement.
    
        Returns a dictionary:
        {
            "required_credits": float,
            "source": str,
            "source_groups": str
        }
        """
    
        if applicable_groups.empty:
            return None
    
        df = applicable_groups.copy()
    
        if "rule_type" not in df.columns:
            return None
    
        df["rule_type_normalized"] = (
            df["rule_type"]
            .astype(str)
            .str.strip()
        )
    
        df["requirement_area_normalized"] = (
            df.get("requirement_area", "")
            .astype(str)
            .str.strip()
        )
    
        profile_option_id = str(
            self.profile.option_id or ""
        ).strip().upper()
    
        if "option_id" not in df.columns:
            df["option_id"] = ""
    
        df["option_id_normalized"] = (
            df["option_id"]
            .astype(str)
            .str.strip()
            .str.upper()
        )
    
        # 1. Prefer option-specific minimum-credit rows.
        option_specific = df[
            (df["rule_type_normalized"] == "option_minimum_credits")
            & (df["option_id_normalized"] == profile_option_id)
            & (df["option_id_normalized"] != "")
        ].copy()
    
        if not option_specific.empty:
            required = option_specific["credits"].max()
    
            return {
                "required_credits": float(required),
                "source": "option_minimum_credits_option_specific",
                "source_groups": option_specific
            }
    
        # 2. Fall back to generic option minimums.
        generic_option_minimums = df[
            (df["rule_type_normalized"] == "option_minimum_credits")
            & (df["option_id_normalized"] == "")
        ].copy()
    
        if not generic_option_minimums.empty:
            required = generic_option_minimums["credits"].max()
    
            return {
                "required_credits": float(required),
                "source": "option_minimum_credits_generic",
                "source_groups": generic_option_minimums
            }
    
        # 3. Fall back to summing table-split AoC credit rows.
        table_aoc_rows = df[
            df["rule_type_normalized"] == "area_of_concentration_credits"
        ].copy()
    
        if not table_aoc_rows.empty:
            required = table_aoc_rows["credits"].sum()
    
            return {
                "required_credits": float(required),
                "source": "summed_area_of_concentration_credits_rows",
                "source_groups": table_aoc_rows
            }
    
        return None
    
    
    def _audit_canonical_credit_requirement(
        self,
        courses: pd.DataFrame,
        source_groups: pd.DataFrame,
        requirement_area: str,
        synthetic_label: str,
        synthetic_rule_type: str,
        synthetic_suffix: str,
        required_credits: float,
        eligible_courses: list[str],
        option_id: str = "",
        option_name: str = "",
        notes_prefix: str = ""
    ) -> dict | None:
        if required_credits <= 0:
            return None
    
        matched = self._match_courses_to_eligible_list(
            courses=courses,
            eligible_course_codes=eligible_courses
        )
    
        completed_credits = matched["credits"].sum()
    
        synthetic_group = self._make_synthetic_group(
            requirement_area=requirement_area,
            label=synthetic_label,
            rule_type=synthetic_rule_type,
            suffix=synthetic_suffix,
            option_id=option_id,
            option_name=option_name
        )
    
        source_group_ids = self.resolver.join_group_ids(source_groups)
    
        notes = (
            f"{notes_prefix} Source group IDs: {source_group_ids}. "
            f"Eligible courses: {len(set(eligible_courses))}."
        )
    
        return self._make_summary_row_from_values(
            group=synthetic_group,
            completed=completed_credits,
            required=required_credits,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes=notes
        )
    
    def _audit_canonical_course_count_requirement(
        self,
        courses: pd.DataFrame,
        source_groups: pd.DataFrame,
        requirement_area: str,
        synthetic_label: str,
        synthetic_rule_type: str,
        synthetic_suffix: str,
        required_courses: float,
        required_credits: float,
        eligible_courses: list[str] | None = None,
        notes_prefix: str = ""
    ) -> dict | None:
        if source_groups.empty:
            return None
    
        if eligible_courses is None:
            eligible_courses = self.resolver.get_course_codes_for_groups(source_groups)
    
        matched = self._match_courses_to_eligible_list(
            courses=courses,
            eligible_course_codes=eligible_courses
        )
    
        matched_course_count = (
            matched["effective_course_code"]
            .drop_duplicates()
            .shape[0]
        )
    
        matched_credits = matched["credits"].sum()
    
        completed = min(matched_course_count, required_courses)
    
        synthetic_group = self._make_synthetic_group(
            requirement_area=requirement_area,
            label=synthetic_label,
            rule_type=synthetic_rule_type,
            suffix=synthetic_suffix
        )
    
        source_group_ids = self.resolver.join_group_ids(source_groups)
    
        notes = (
            f"{notes_prefix} Source group IDs: {source_group_ids}. "
            f"Eligible courses: {len(set(eligible_courses))}."
        )
    
        return self._make_summary_row_from_values(
            group=synthetic_group,
            completed=completed,
            required=required_courses,
            unit="course",
            matched_courses=self._course_list(matched),
            notes=notes,
            completed_credits=matched_credits,
            required_credits=required_credits
        )
    
    def _audit_canonical_tools_elective(
        self,
        courses: pd.DataFrame,
        applicable_groups: pd.DataFrame
    ) -> dict | None:
        tools_groups = self.resolver.get_groups_by_requirement_area(
            applicable_groups,
            "Tools Elective"
        )
    
        if tools_groups.empty:
            return None
    
        required_courses = self._resolve_tools_required_course_count(
            tools_groups
        )
    
        required_credits = self._resolve_tools_required_credits(
            tools_groups=tools_groups,
            required_courses=required_courses
        )
    
        return self._audit_canonical_course_count_requirement(
            courses=courses,
            source_groups=tools_groups,
            requirement_area="Tools Elective",
            synthetic_label="Tools Elective total",
            synthetic_rule_type="tools_elective_total",
            synthetic_suffix="TOOLS_ELECTIVE_CANONICAL_TOTAL",
            required_courses=required_courses,
            required_credits=required_credits,
            notes_prefix="Canonical Tools Elective requirement."
        )
    
    def _resolve_tools_required_course_count(
        self,
        tools_groups: pd.DataFrame
    ) -> float:
        if tools_groups.empty:
            return 0
    
        rule_values = pd.to_numeric(
            tools_groups["rule_value"],
            errors="coerce"
        ).dropna()
    
        if not rule_values.empty:
            return float(rule_values.max())
    
        credits = pd.to_numeric(
            tools_groups["credits"],
            errors="coerce"
        ).dropna()
    
        if not credits.empty:
            return float(credits.sum() / 3)
    
        return 1.0
    
    def _resolve_tools_required_credits(
        self,
        tools_groups: pd.DataFrame,
        required_courses=None
    ) -> float:
        if tools_groups.empty:
            return 0
    
        credits = pd.to_numeric(
            tools_groups["credits"],
            errors="coerce"
        ).dropna()
    
        if not credits.empty:
            total = float(credits.sum())
    
            if required_courses is not None:
                minimum_expected = float(required_courses) * 3
    
                if total < minimum_expected:
                    return minimum_expected
    
            return total
    
        if required_courses is not None:
            return float(required_courses) * 3
    
        return 0
    
    def _make_synthetic_group(
        self,
        requirement_area: str,
        label: str,
        rule_type: str,
        suffix: str,
        option_id: str = "",
        option_name: str = "",
        theme: str = ""
    ) -> pd.Series:
        program = str(self.profile.program).strip().upper()
        calendar_year = str(self.profile.calendar_year).strip()
        program_type = str(self.profile.program_type).strip().upper()
    
        group_id = (
            f"{program}_{calendar_year}_{program_type}_{suffix}"
        )
    
        return pd.Series(
            {
                "group_id": group_id.replace("-", "_").replace(" ", "_").upper(),
                "requirement_area": requirement_area,
                "option_id": option_id,
                "option_name": option_name,
                "theme": theme,
                "label": label,
                "rule_type": rule_type,
            }
        )
    
    def _get_selected_option_name(
        self,
        applicable_groups: pd.DataFrame
    ) -> str:
        """
        Try to get a display option name for the selected option_id.
        """
    
        option_id = str(self.profile.option_id or "").strip().upper()
    
        if not option_id:
            return ""
    
        if "option_id" not in applicable_groups.columns:
            return ""
    
        option_rows = applicable_groups[
            applicable_groups["option_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            == option_id
        ]
    
        if option_rows.empty:
            return ""
    
        if "option_name" not in option_rows.columns:
            return ""
    
        names = (
            option_rows["option_name"]
            .dropna()
            .astype(str)
            .str.strip()
        )
    
        names = names[names != ""]
    
        if names.empty:
            return ""
    
        return names.iloc[0]