# -*- coding: utf-8 -*-
"""
Created on Wed Jul  8 11:36:50 2026

@author: Tim Rodgers w M365 CoPilot

Faculty-level auditor for the degree audit pipeline.

Checks:
- Total credits
- Science credits
- Arts credits
- Upper-level credits
- Upper-level Science credits
- Science Breadth
- Communication Requirement
- Laboratory Science Requirement

Inputs:
- classified_courses dataframe
- faculty_requirement_rules.csv
- AuditInputBundle profile/options
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


class FacultyAuditor:
    """
    Audits Faculty-level requirements using classified course data.
    """

    def __init__(
        self,
        faculty_requirement_rules: pd.DataFrame,
        profile,
        options,
        requirement_groups: pd.DataFrame | None = None,
    ):
        self.faculty_requirement_rules = (
            faculty_requirement_rules.copy().fillna("")
        )

        self.profile = profile
        self.options = options

        self.faculty_requirement_rules["value"] = pd.to_numeric(
            self.faculty_requirement_rules["value"],
            errors="coerce"
        )
        
        self.requirement_groups = (
            requirement_groups.copy().fillna("")
            if requirement_groups is not None
            else pd.DataFrame()
        )

    @classmethod
    def from_audit_bundle(cls, bundle):
        """
        Build a FacultyAuditor from an AuditInputBundle.
        """

        faculty_files = bundle.faculty_requirements.files

        if "faculty_requirement_rules" not in faculty_files:
            raise KeyError(
                "Missing faculty_requirement_rules.csv in faculty requirements."
            )

        return cls(
            faculty_requirement_rules=faculty_files[
                "faculty_requirement_rules"
            ],
            profile=bundle.profile,
            options=bundle.options,
            requirement_groups=bundle.specialization_requirements.requirement_groups,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def audit(
        self,
        classified_courses: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Run Faculty-level audit.

        Returns
        -------
        pd.DataFrame
            One row per Faculty requirement.
        """

        counted_courses = self._filter_counted_courses(
            classified_courses
        )

        rows = []

        rows.append(
            self._audit_total_credits(counted_courses)
        )

        rows.append(
            self._audit_science_credits(counted_courses)
        )

        rows.append(
            self._audit_arts_credits(counted_courses)
        )
        
        rows.append(
            self._audit_other_faculty_credits_cap(counted_courses)
        )

        rows.append(
            self._audit_upper_level_total(counted_courses)
        )

        rows.append(
            self._audit_upper_level_science(counted_courses)
        )

        rows.append(
            self._audit_science_breadth(counted_courses)
        )

        rows.append(
            self._audit_lab_requirement(counted_courses)
        )

        rows.append(
            self._audit_communication_requirement(counted_courses)
        )

        return pd.DataFrame(rows)

    def print_summary(
        self,
        faculty_audit_summary: pd.DataFrame
    ) -> None:
        """
        Print a readable terminal summary.
        """

        print()
        print("Faculty Requirement Audit")
        print("=========================")

        for _, row in faculty_audit_summary.iterrows():
            requirement_id = row.get("requirement_id", "")
            status = row.get("status", "")
            completed = row.get("completed", "")
            required = row.get("required", "")
            remaining = row.get("remaining", "")
            surplus = row.get("surplus", "")
            unit = row.get("unit", "")
            notes = row.get("notes", "")

            print(
                f"{requirement_id}: {status} "
                f"({completed}/{required} {unit})"
            )

            if notes:
                print(f"  Notes: {notes}")

        print()

    def write_summary(
        self,
        faculty_audit_summary: pd.DataFrame,
        output_dir: str | Path,
        filename: str = "faculty_audit_summary.csv"
    ) -> Path:
        """
        Write Faculty audit summary to CSV.
        """

        output_dir = Path(output_dir)

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        output_path = output_dir / filename

        faculty_audit_summary.to_csv(
            output_path,
            index=False
        )

        return output_path

    # ------------------------------------------------------------------
    # Individual audits
    # ------------------------------------------------------------------

    def _audit_total_credits(
        self,
        courses: pd.DataFrame
    ) -> dict:
        required, notes = self._resolve_total_credits_required()
    
        completed = courses["credits"].sum()
    
        return self._make_summary_row(
            requirement_id="TOTAL_CREDITS",
            requirement_area="Faculty Requirement",
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(courses),
            notes=notes
        )

    def _audit_science_credits(
        self,
        courses: pd.DataFrame
    ) -> dict:
        rule = self._get_rule_by_type("min_science_credits")

        required = self._rule_value(rule)

        matched = courses[
            courses["is_science_credit"] == True
        ]

        completed = matched["credits"].sum()

        return self._make_summary_row(
            requirement_id="SCIENCE_CREDITS",
            requirement_area="Faculty Requirement",
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes="Science credits based on faculty course classification rules."
        )

    def _audit_arts_credits(
        self,
        courses: pd.DataFrame
    ) -> dict:
        rule = self._get_rule_by_type("min_arts_credits")

        required = self._rule_value(rule)

        matched = courses[
            courses["is_arts_credit"] == True
        ]

        completed = matched["credits"].sum()

        return self._make_summary_row(
            requirement_id="ARTS_CREDITS",
            requirement_area="Faculty Requirement",
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes="Arts credits based on faculty course classification rules."
        )

    def _audit_upper_level_total(
        self,
        courses: pd.DataFrame
    ) -> dict:
        rule = self._get_rule_by_type("min_upper_level_credits")

        required = self._rule_value(rule)

        matched = courses[
            courses["is_upper_level"] == True
        ]

        completed = matched["credits"].sum()

        return self._make_summary_row(
            requirement_id="UPPER_LEVEL_TOTAL",
            requirement_area="Faculty Requirement",
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes="Upper-level means 300-level or above."
        )

    def _audit_upper_level_science(
        self,
        courses: pd.DataFrame
    ) -> dict:
        rule = self._get_rule_by_type(
            "min_upper_level_science_credits"
        )

        required = self._rule_value(rule)

        matched = courses[
            (courses["is_upper_level"] == True)
            & (courses["is_science_credit"] == True)
        ]

        completed = matched["credits"].sum()

        return self._make_summary_row(
            requirement_id="UPPER_LEVEL_SCIENCE",
            requirement_area="Faculty Requirement",
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes=(
                "Upper-level Science requirement depends on program type; "
                f"current program type is {self.profile.program_type}."
            )
        )

    def _audit_science_breadth(
        self,
        courses: pd.DataFrame
    ) -> dict:
        rule = self._get_rule_by_type("min_breadth_categories")

        required = self._rule_value(rule)

        category_credit_totals = {}

        for _, row in courses.iterrows():
            categories = self._split_semicolon(
                row.get("breadth_categories", "")
            )

            credits = row.get("credits", 0)

            if pd.isna(credits):
                credits = 0

            for category in categories:
                category_credit_totals[category] = (
                    category_credit_totals.get(category, 0) + float(credits)
                )

        completed_categories = [
            category
            for category, credits in category_credit_totals.items()
            if credits >= 3
        ]

        completed = len(completed_categories)

        notes = (
            "Completed categories with at least 3 credits: "
            + "; ".join(sorted(completed_categories))
        )

        return self._make_summary_row(
            requirement_id="SCIENCE_BREADTH",
            requirement_area="Faculty Requirement",
            completed=completed,
            required=required,
            unit="categories",
            matched_courses="",
            notes=notes
        )

    def _audit_lab_requirement(
        self,
        courses: pd.DataFrame
    ) -> dict:
        rule = self._get_rule_by_id("LAB_REQUIREMENT")

        required = self._rule_value(rule)

        matched = courses[
            courses["is_lab_course"] == True
        ]

        completed = len(
            matched["effective_course_code"].dropna().unique()
        )

        return self._make_summary_row(
            requirement_id="LAB_REQUIREMENT",
            requirement_area="Faculty Requirement",
            completed=completed,
            required=required,
            unit="course",
            matched_courses=self._course_list(matched),
            notes="Satisfied if at least one laboratory science course is counted."
        )

    def _audit_communication_requirement(
        self,
        courses: pd.DataFrame
    ) -> dict:
        rule = self._get_rule_by_id("COMMUNICATION")

        required = self._rule_value(rule)

        matched = courses[
            courses["is_communication_course"] == True
        ]

        completed = matched["credits"].sum()

        return self._make_summary_row(
            requirement_id="COMMUNICATION",
            requirement_area="Faculty Requirement",
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes="Communication requirement satisfied by mapped communication courses."
        )

    def _audit_other_faculty_credits_cap(
        self,
        courses: pd.DataFrame
    ) -> dict | None:
        """
        Audit the cap on credits from faculties other than Science or Arts.
    
        First-pass definition:
        other_faculty_credits = courses where neither is_science_credit nor is_arts_credit.
        """
    
        rule = self._get_rule_by_type("max_other_faculty_credits")
    
        if rule is None:
            return None
    
        maximum_allowed = self._rule_value(rule)
    
        matched = courses[
            (courses["is_science_credit"] == False)
            & (courses["is_arts_credit"] == False)
        ].copy()
    
        completed = matched["credits"].sum()
    
        return self._make_maximum_summary_row(
            requirement_id="OTHER_FACULTY_CREDITS_CAP",
            requirement_area="Faculty Requirement",
            completed=completed,
            maximum_allowed=maximum_allowed,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes=(
                "Credits where is_science_credit and is_arts_credit are both False. "
                "First-pass proxy for credits from faculties other than Science or Arts."
            )
        )

    # ------------------------------------------------------------------
    # Rule helpers
    # ------------------------------------------------------------------

    def _get_rule_by_id(
        self,
        requirement_id: str
    ) -> Optional[pd.Series]:
        df = self.faculty_requirement_rules.copy()

        df = df[
            df["requirement_id"].astype(str).str.upper()
            == requirement_id.upper()
        ]

        df = self._filter_rules_by_program_context(df)

        if df.empty:
            return None

        return df.iloc[0]

    def _get_rule_by_type(
        self,
        rule_type: str
    ) -> Optional[pd.Series]:
        df = self.faculty_requirement_rules.copy()

        df = df[
            df["rule_type"].astype(str).str.lower()
            == rule_type.lower()
        ]

        df = self._filter_rules_by_program_context(df)

        if df.empty:
            return None

        return df.iloc[0]

    def _filter_rules_by_program_context(
        self,
        df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Filter rule rows to match the student's program type.

        Priority:
        1. Exact program type, e.g. Major or Honours
        2. MajorOrHonours
        3. All
        """

        if df.empty:
            return df

        if "program_context" not in df.columns:
            return df

        program_type = str(
            self.profile.program_type
        ).strip().lower()

        df = df.copy()

        df["program_context_normalized"] = (
            df["program_context"]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        exact = df[
            df["program_context_normalized"] == program_type
        ]

        if not exact.empty:
            return exact

        if program_type in {"major", "honours"}:
            major_or_honours = df[
                df["program_context_normalized"] == "majororhonours"
            ]

            if not major_or_honours.empty:
                return major_or_honours

        all_rows = df[
            df["program_context_normalized"] == "all"
        ]

        if not all_rows.empty:
            return all_rows

        return df

    @staticmethod
    def _rule_value(
        rule: Optional[pd.Series]
    ) -> float:
        if rule is None:
            return 0

        value = rule.get("value", 0)

        if pd.isna(value):
            return 0

        return float(value)

    def _resolve_total_credits_required(self) -> tuple[float, str]:
        """
        Resolve total degree credits.
    
        Uses the larger of:
        - Faculty minimum total credits from faculty_requirement_rules.csv
        - Specialization minimum_degree_credits from requirement_groups.csv
        """
    
        faculty_rule = self._get_rule_by_type("min_total_credits")
        faculty_minimum = self._rule_value(faculty_rule)
    
        specialization_minimum = self._get_specialization_min_degree_credits()
    
        required = max(faculty_minimum, specialization_minimum)
    
        notes = (
            f"Faculty minimum={faculty_minimum}; "
            f"specialization minimum={specialization_minimum}; "
            f"using required total={required}."
        )
    
        return required, notes
    
    def _get_specialization_min_degree_credits(self) -> float:
        """
        Get the specialization-specific minimum degree credits from requirement_groups.csv.
        """
    
        if self.requirement_groups.empty:
            return 0
    
        df = self.requirement_groups.copy()
    
        required_columns = [
            "program",
            "calendar_year",
            "program_type",
            "rule_type",
            "credits",
        ]
    
        for column in required_columns:
            if column not in df.columns:
                return 0
    
        profile_program = str(self.profile.program).strip().upper()
        profile_calendar_year = str(self.profile.calendar_year).strip()
        profile_program_type = str(self.profile.program_type).strip().upper()
    
        df["program_normalized"] = df["program"].astype(str).str.strip().str.upper()
        df["calendar_year_normalized"] = df["calendar_year"].astype(str).str.strip()
        df["program_type_normalized"] = (
            df["program_type"].astype(str).str.strip().str.upper()
        )
        df["rule_type_normalized"] = df["rule_type"].astype(str).str.strip()
    
        matched = df[
            (df["program_normalized"] == profile_program)
            & (df["calendar_year_normalized"] == profile_calendar_year)
            & (df["program_type_normalized"] == profile_program_type)
            & (df["rule_type_normalized"] == "minimum_degree_credits")
        ].copy()
    
        if matched.empty:
            return 0
    
        matched["credits"] = pd.to_numeric(
            matched["credits"],
            errors="coerce"
        )
    
        return float(matched["credits"].max())

    # ------------------------------------------------------------------
    # Data filtering and formatting helpers
    # ------------------------------------------------------------------

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

    @staticmethod
    def _make_summary_row(
        requirement_id: str,
        requirement_area: str,
        completed,
        required,
        unit: str,
        matched_courses: str,
        notes: str
    ) -> dict:
        completed_value = float(completed) if completed is not None else 0
        required_value = float(required) if required is not None else 0
        remaining_value = max(required_value - completed_value, 0)
        surplus_value = max(completed_value - required_value, 0)

        if completed_value >= required_value:
            status = "satisfied"
        elif completed_value > 0:
            status = "partial"
        else:
            status = "missing"

        return {
            "requirement_id": requirement_id,
            "requirement_area": requirement_area,
            "status": status,
            "completed": completed_value,
            "required": required_value,
            "remaining": remaining_value,
            "surplus": surplus_value,
            "unit": unit,
            "matched_courses": matched_courses,
            "notes": notes,
        }

    @staticmethod
    def _make_maximum_summary_row(
        requirement_id: str,
        requirement_area: str,
        completed,
        maximum_allowed,
        unit: str,
        matched_courses: str,
        notes: str
    ) -> dict:
        completed_value = float(completed) if completed is not None else 0
        maximum_value = float(maximum_allowed) if maximum_allowed is not None else 0
    
        excess_value = max(completed_value - maximum_value, 0)
        remaining_capacity = max(maximum_value - completed_value, 0)
    
        if completed_value <= maximum_value:
            status = "satisfied"
        else:
            status = "exceeds_limit"
    
        return {
            "requirement_id": requirement_id,
            "requirement_area": requirement_area,
            "status": status,
            "completed": completed_value,
            "required": maximum_value,
            "remaining": remaining_capacity,
            "surplus": excess_value,
            "unit": unit,
            "matched_courses": matched_courses,
            "notes": notes,
        }
    
    @staticmethod
    def _course_list(
        courses: pd.DataFrame
    ) -> str:
        if courses.empty:
            return ""

        values = (
            courses["effective_course_code"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .tolist()
        )

        return ";".join(values)

    @staticmethod
    def _split_semicolon(value) -> list:
        if value is None:
            return []

        return [
            item.strip()
            for item in str(value).split(";")
            if item.strip()
        ]

