# -*- coding: utf-8 -*-
"""
Created on Wed Jul  8 13:44:09 2026
Tim Rodgers with M365 CoPilot

Specialization requirement resolver.

This module centralizes access to specialization requirement metadata from:
- requirement_groups.csv
- requirement_courses.csv
- allocation_config.csv

It is shared by:
- SpecializationAuditor
- AllocationEngine

The resolver should be the source of truth for:
- applicable requirement groups
- group metadata
- eligible course lists
- option/AoC eligible courses
- complementary studies eligible courses
- bucket/requirement-area mappings
- level requirement matching helpers
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .models import AllocationConfig


class SpecializationRequirementResolver:
    """
    Shared resolver for specialization requirement metadata.
    """

    def __init__(
        self,
        requirement_groups: pd.DataFrame,
        requirement_courses: pd.DataFrame,
        profile,
        allocation_config: AllocationConfig | None = None,
    ):
        self.requirement_groups = requirement_groups.copy().fillna("")
        self.requirement_courses = requirement_courses.copy().fillna("")
        self.profile = profile
        self.config = allocation_config or AllocationConfig()

        self._normalize_inputs()

    @classmethod
    def from_audit_bundle(
        cls,
        bundle,
        allocation_config: AllocationConfig | None = None,
    ):
        """
        Build resolver from AuditInputBundle.

        If allocation_config is not provided, use
        bundle.specialization_requirements.allocation_config if available.
        Otherwise use default AllocationConfig.
        """

        if allocation_config is None:
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
            allocation_config=allocation_config,
        )

    # ------------------------------------------------------------------
    # Applicable groups
    # ------------------------------------------------------------------

    def get_applicable_requirement_groups(self) -> pd.DataFrame:
        """
        Return requirement groups applicable to the student's:
        - program
        - program_type
        - selected option_id

        Recommended courses are excluded.
        """

        df = self.requirement_groups.copy()

        profile_program = str(self.profile.program).strip().upper()
        profile_calendar_year = str(self.profile.calendar_year).strip()
        profile_program_type = str(self.profile.program_type).strip().upper()
        profile_option_id = str(self.profile.option_id or "").strip().upper()

        df["program_normalized"] = (
            df["program"].astype(str).str.strip().str.upper()
        )

        df["calendar_year_normalized"] = (
            df["calendar_year"].astype(str).str.strip()
        )

        df["program_type_normalized"] = (
            df["program_type"].astype(str).str.strip().str.upper()
        )

        df["option_id_normalized"] = (
            df["option_id"].astype(str).str.strip().str.upper()
        )

        df = df[
            (
                (df["program_normalized"] == profile_program)
                | (df["program_normalized"] == "ALL")
                | (df["program_normalized"] == "")
            )
            &
            (
                (df["calendar_year_normalized"] == profile_calendar_year)
                | (df["calendar_year_normalized"] == "ALL")
                | (df["calendar_year_normalized"] == "")
            )
            &
            (
                (df["program_type_normalized"] == profile_program_type)
                | (df["program_type_normalized"] == "ALL")
                | (df["program_type_normalized"] == "")
            )
            &
            (
                (df["option_id_normalized"] == profile_option_id)
                | (df["option_id_normalized"] == "")
            )
        ].copy()

        if "is_recommended" in df.columns:
            df = df[
                df["is_recommended"].astype(str).str.lower() != "true"
            ].copy()

        return df

    def get_group_metadata(
        self,
        group_id: str,
    ) -> dict:
        """
        Return original requirement_groups row metadata for group_id.
        """

        rows = self.requirement_groups[
            self.requirement_groups["group_id"].astype(str) == str(group_id)
        ]

        if rows.empty:
            return {}

        return rows.iloc[0].to_dict()

    def get_group_series(
        self,
        group_id: str,
    ) -> pd.Series:
        """
        Return original requirement_groups row as Series.

        Raises if group_id is missing.
        """

        metadata = self.get_group_metadata(group_id)

        if not metadata:
            raise KeyError(
                f"No requirement group found for group_id={group_id}"
            )

        return pd.Series(metadata)

    # ------------------------------------------------------------------
    # Bucket/config helpers
    # ------------------------------------------------------------------

    def areas_for_bucket(
        self,
        bucket: str,
    ) -> list:
        return self.config.requirement_area_map.get(bucket, [])

    def display_name_for_bucket(
        self,
        bucket: str,
    ) -> str:
        return self.config.bucket_display_names.get(bucket, bucket)

    def rule_types_for_bucket(
        self,
        bucket: str,
    ) -> list:
        return self.config.canonical_rule_type_map.get(bucket, [])

    def bucket_for_row(
        self,
        row,
    ) -> str:
        requirement_area = str(row.get("requirement_area", "")).strip()
        rule_type = str(row.get("rule_type", "")).strip()

        for bucket in self.config.priority_order:
            if requirement_area in self.areas_for_bucket(bucket):
                return bucket

            if rule_type in self.rule_types_for_bucket(bucket):
                return bucket

        return ""

    def df_for_bucket(
        self,
        df: pd.DataFrame,
        bucket: str,
    ) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=df.columns if df is not None else [])

        areas = self.areas_for_bucket(bucket)
        rule_types = self.rule_types_for_bucket(bucket)

        return df[
            df["requirement_area"].astype(str).str.strip().isin(areas)
            |
            df["rule_type"].astype(str).str.strip().isin(rule_types)
        ].copy()

    def canonical_rows_for_bucket(
        self,
        df: pd.DataFrame,
        bucket: str,
    ) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=df.columns if df is not None else [])

        rule_types = self.rule_types_for_bucket(bucket)

        if not rule_types:
            return pd.DataFrame(columns=df.columns)

        return df[
            df["rule_type"].astype(str).str.strip().isin(rule_types)
        ].copy()

    def get_groups_by_requirement_area(
        self,
        applicable_groups: pd.DataFrame,
        requirement_area: str,
    ) -> pd.DataFrame:
        if applicable_groups is None or applicable_groups.empty:
            return pd.DataFrame(
                columns=applicable_groups.columns
                if applicable_groups is not None
                else []
            )

        rows = applicable_groups[
            applicable_groups["requirement_area"]
            .astype(str)
            .str.strip()
            == requirement_area
        ].copy()

        if "is_recommended" in rows.columns:
            rows = rows[
                rows["is_recommended"].astype(str).str.lower() != "true"
            ].copy()

        return rows

    def normalize_override_area_to_bucket(
        self,
        override_area: str,
    ) -> tuple[str, str]:
        """
        Return (bucket, display_area).

        Allows override_exclusive_requirement_area to be either:
        - generic bucket name, e.g. option
        - requirement_area display name, e.g. Area of Concentration
        """

        value = str(override_area).strip()

        if not value:
            return "", ""

        value_lower = value.lower()

        for bucket in self.config.requirement_area_map:
            if value_lower == bucket.lower():
                return bucket, self.display_name_for_bucket(bucket)

        for bucket, areas in self.config.requirement_area_map.items():
            for area in areas:
                if value_lower == area.lower():
                    return bucket, area

        return value, value

    # ------------------------------------------------------------------
    # Course-code lookup helpers
    # ------------------------------------------------------------------

    def get_group_course_codes(
        self,
        group_id: str,
    ) -> list:
        rows = self.requirement_courses[
            self.requirement_courses["group_id"].astype(str) == str(group_id)
        ]

        return (
            rows["course_code"]
            .dropna()
            .astype(str)
            .str.strip()
            .drop_duplicates()
            .tolist()
        )

    def get_course_codes_for_groups(
        self,
        groups: pd.DataFrame,
    ) -> list:
        if groups is None or groups.empty:
            return []

        group_ids = (
            groups["group_id"]
            .dropna()
            .astype(str)
            .tolist()
        )

        rows = self.requirement_courses[
            self.requirement_courses["group_id"].astype(str).isin(group_ids)
        ]

        return (
            rows["course_code"]
            .dropna()
            .astype(str)
            .str.strip()
            .drop_duplicates()
            .tolist()
        )

    def get_eligible_courses_by_bucket(
        self,
        bucket: str,
    ) -> list:
        areas = self.areas_for_bucket(bucket)

        rows = self.requirement_courses[
            self.requirement_courses["requirement_area"]
            .astype(str)
            .str.strip()
            .isin(areas)
        ]

        return (
            rows["course_code"]
            .dropna()
            .astype(str)
            .str.strip()
            .drop_duplicates()
            .tolist()
        )

    def get_option_eligible_course_codes(
        self,
        option_id: str,
    ) -> list:
        """
        Return eligible courses for selected option-like bucket.

        Default ENSC meaning:
        bucket = option
        requirement_area = Area of Concentration
        """

        profile_program = str(self.profile.program).strip().upper()
        profile_calendar_year = str(self.profile.calendar_year).strip()
        profile_program_type = str(self.profile.program_type).strip().upper()

        rows = self.requirement_courses.copy()

        rows["program_normalized"] = (
            rows["program"].astype(str).str.strip().str.upper()
        )

        rows["calendar_year_normalized"] = (
            rows["calendar_year"].astype(str).str.strip()
        )

        rows["program_type_normalized"] = (
            rows["program_type"].astype(str).str.strip().str.upper()
        )

        rows["option_id_normalized"] = (
            rows["option_id"].astype(str).str.strip().str.upper()
        )

        option_areas = self.areas_for_bucket("option")

        rows = rows[
            rows["requirement_area"].astype(str).str.strip().isin(option_areas)
            &
            (rows["option_id_normalized"] == str(option_id).strip().upper())
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
                rows["is_recommended"].astype(str).str.lower() != "true"
            )
        ].copy()

        return (
            rows["course_code"]
            .dropna()
            .astype(str)
            .str.strip()
            .drop_duplicates()
            .tolist()
        )

    def get_complementary_studies_eligible_course_codes(self) -> list:
        """
        Return eligible courses for complementary bucket.
        """

        areas = self.areas_for_bucket("complementary")

        rows = self.requirement_courses[
            self.requirement_courses["requirement_area"]
            .astype(str)
            .str.strip()
            .isin(areas)
        ]

        return (
            rows["course_code"]
            .dropna()
            .astype(str)
            .str.strip()
            .drop_duplicates()
            .tolist()
        )

    # ------------------------------------------------------------------
    # Course matching helpers
    # ------------------------------------------------------------------

    @staticmethod
    def course_matches_any_eligible(
        student_code: str,
        eligible_course_codes,
    ) -> bool:
        if not student_code:
            return False

        for eligible in eligible_course_codes:
            eligible = str(eligible).strip().upper()

            if not eligible:
                continue

            if eligible.endswith("*"):
                prefix = eligible.replace("*", "")

                if str(student_code).strip().upper().startswith(prefix):
                    return True

            elif str(student_code).strip().upper() == eligible:
                return True

        return False

    def filter_courses_by_eligible_codes(
        self,
        courses: pd.DataFrame,
        eligible_course_codes: list[str],
    ) -> pd.DataFrame:
        if courses is None or courses.empty:
            return pd.DataFrame(columns=courses.columns if courses is not None else [])

        eligible_set = {
            str(code).strip().upper()
            for code in eligible_course_codes
            if str(code).strip()
        }

        indices = []

        for idx, row in courses.iterrows():
            student_code = str(row.get("effective_course_code", "")).strip().upper()

            if self.course_matches_any_eligible(student_code, eligible_set):
                indices.append(idx)

        return courses.loc[indices].copy()

    def course_matches_level_requirement(
        self,
        course_row,
        group_row,
    ) -> bool:
        """
        Check if one course row satisfies one level_requirement group row.
        """

        rule_subjects = self.split_semicolon(
            group_row.get("rule_subject", "")
        )

        include_pattern = str(
            group_row.get("include_pattern", "")
        ).strip()

        exclude_pattern = str(
            group_row.get("exclude_pattern", "")
        ).strip()

        level_min, level_max = self.level_bounds_from_include_pattern(
            include_pattern
        )

        if level_min is None or level_max is None:
            return False

        excluded_courses = {
            item.strip().upper()
            for item in str(exclude_pattern).split(";")
            if item.strip()
        }

        normalized_subjects = {
            subject.strip().upper()
            for subject in rule_subjects
            if subject.strip()
        }

        subject = str(course_row.get("subject", "")).strip().upper()
        code = str(course_row.get("effective_course_code", "")).strip().upper()

        course_number = pd.to_numeric(
            course_row.get("course_number", None),
            errors="coerce",
        )

        if pd.isna(course_number):
            return False

        if subject not in normalized_subjects:
            return False

        if not (level_min <= course_number <= level_max):
            return False

        if code in excluded_courses:
            return False

        return True

    def match_courses_to_level_requirement(
        self,
        courses: pd.DataFrame,
        group_row,
    ) -> pd.DataFrame:
        if courses is None or courses.empty:
            return pd.DataFrame(columns=courses.columns if courses is not None else [])

        indices = []

        for idx, course_row in courses.iterrows():
            if self.course_matches_level_requirement(course_row, group_row):
                indices.append(idx)

        return courses.loc[indices].copy()

    # ------------------------------------------------------------------
    # Generic utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def split_semicolon(value) -> list:
        if value is None:
            return []

        return [
            item.strip()
            for item in str(value).split(";")
            if item.strip()
        ]

    @staticmethod
    def level_bounds_from_include_pattern(
        include_pattern: str,
    ) -> tuple[Optional[int], Optional[int]]:
        import re

        text = str(include_pattern).strip().lower()

        match = re.match(
            r"^(\d)00-level$",
            text,
        )

        if not match:
            return None, None

        lower = int(match.group(1)) * 100

        return lower, lower + 99

    # ------------------------------------------------------------------
    # Normalization
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

        for column in [
            "credits",
            "rule_value",
        ]:
            if column in self.requirement_groups.columns:
                self.requirement_groups[column] = pd.to_numeric(
                    self.requirement_groups[column],
                    errors="coerce",
                )

            if column in self.requirement_courses.columns:
                self.requirement_courses[column] = pd.to_numeric(
                    self.requirement_courses[column],
                    errors="coerce",
                )
                

    @staticmethod
    def join_group_ids(groups: pd.DataFrame) -> str:
        """
        Join unique group_id values from a dataframe into a semicolon-separated string.
    
        Used for notes/source tracing in auditors.
        """
    
        if groups is None or groups.empty:
            return ""
    
        if "group_id" not in groups.columns:
            return ""
    
        return ";".join(
            groups["group_id"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .tolist()
        )