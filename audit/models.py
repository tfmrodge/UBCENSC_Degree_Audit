# -*- coding: utf-8 -*-
"""
Created on 2026-07-07

@author: Tim Rodgers with MS Copilot
Core data models for the UBC ENSC degree audit engine.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

@dataclass
class StudentProfile:
    """
    Metadata describing the student's audit case.

    This should describe the student/program/calendar context.
    Runtime options such as count_statuses should be supplied separately.
    """

    case_id: str
    calendar_year: str
    program: str
    program_type: str

    option_id: Optional[str] = None
    academic_year: Optional[int] = None
    start_date: Optional[str] = None

    has_biology_12: Optional[bool] = None
    has_chemistry_12: Optional[bool] = None
    has_physics_12: Optional[bool] = None

    raw: dict = field(default_factory=dict)


@dataclass
class AuditOptions:
    """
    Runtime audit options.

    These should be set when running the audit, not in student_profile.csv.
    """

    count_statuses: list[str] = field(
        default_factory=lambda: ["completed", "in_progress", "planned"]
    )

    audit_mode: str = "planning"
    include_failed: bool = False
    include_withdrawn: bool = False


@dataclass
class StudentCourseData:
    """
    Normalized student course dataframe.
    """

    courses: pd.DataFrame
    source_path: Optional[Path] = None


@dataclass
class SpecializationRequirementData:
    """
    Requirement groups and requirement courses for a calendar/program package.
    """

    requirement_groups: pd.DataFrame
    requirement_courses: pd.DataFrame
    source_dir: Path
    allocation_config: Optional[pd.DataFrame] = None


@dataclass
class FacultyRequirementData:
    """
    Faculty-level requirement files.

    Stored as a dictionary of dataframe objects keyed by filename stem.
    """

    files: dict[str, pd.DataFrame] = field(default_factory=dict)
    source_dir: Optional[Path] = None


@dataclass
class AuditInputBundle:
    """
    Complete bundle consumed by the audit engine.
    """

    profile: StudentProfile
    student_courses: StudentCourseData
    specialization_requirements: SpecializationRequirementData
    faculty_requirements: FacultyRequirementData
    options: AuditOptions
    
@dataclass
class AuditWorkingData:
    """
    Intermediate working data created during an audit run.
    """
    bundle: AuditInputBundle
    classified_courses: pd.DataFrame | None = None
    faculty_audit_summary: pd.DataFrame | None = None
    specialization_audit: pd.DataFrame | None = None
    course_allocation: pd.DataFrame | None = None
    promotion_audit: pd.DataFrame | None = None

@dataclass
class AllocationConfig:
    """
    Configuration for exclusive course allocation.

    This maps program/specialization-specific requirement names into generic
    allocation buckets used by AllocationEngine.
    """

    priority_order: list[str] = field(
        default_factory=lambda: [
            "core",
            "tools",
            "option",
            "complementary",
            "electives",
        ]
    )

    requirement_area_map: dict[str, list[str]] = field(
        default_factory=lambda: {
            "core": ["Core Requirement"],
            "tools": ["Tools Elective"],
            "option": ["Area of Concentration"],
            "complementary": ["Complementary Studies"],
            "electives": ["Electives"],
        }
    )

    canonical_rule_type_map: dict[str, list[str]] = field(
        default_factory=lambda: {
            "tools": ["tools_elective_total"],
            "option": ["option_total_credits"],
            "complementary": ["complementary_studies_credits"],
        }
    )

    bucket_display_names: dict[str, str] = field(
        default_factory=lambda: {
            "core": "Core Requirement",
            "tools": "Tools Elective",
            "option": "Area of Concentration",
            "complementary": "Complementary Studies",
            "electives": "Electives",
        }
    )

    residual_bucket: str = "electives"
    residual_label: str = "Residual elective / unallocated counted course"

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame):
        """
        Build AllocationConfig from allocation_config.csv.

        Expected columns:
        - bucket
        - priority
        - display_name
        - requirement_areas
        - canonical_rule_types
        - notes

        Optional columns:
        - residual_bucket
        - residual_label
        """

        if df is None or df.empty:
            return cls()

        df = df.copy().fillna("")

        required_columns = [
            "bucket",
            "priority",
            "display_name",
            "requirement_areas",
            "canonical_rule_types",
        ]

        for column in required_columns:
            if column not in df.columns:
                raise ValueError(
                    f"allocation_config.csv is missing required column: {column}"
                )

        priority_order = []
        requirement_area_map = {}
        canonical_rule_type_map = {}
        bucket_display_names = {}

        df["priority_numeric"] = pd.to_numeric(
            df["priority"],
            errors="coerce"
        )

        df = df.sort_values(
            by=["priority_numeric", "bucket"]
        )

        for _, row in df.iterrows():
            bucket = str(row.get("bucket", "")).strip()

            if not bucket:
                continue

            priority_order.append(bucket)

            display_name = str(row.get("display_name", "")).strip()

            if display_name:
                bucket_display_names[bucket] = display_name
            else:
                bucket_display_names[bucket] = bucket

            requirement_areas = [
                item.strip()
                for item in str(row.get("requirement_areas", "")).split(";")
                if item.strip()
            ]

            requirement_area_map[bucket] = requirement_areas

            canonical_rule_types = [
                item.strip()
                for item in str(row.get("canonical_rule_types", "")).split(";")
                if item.strip()
            ]

            canonical_rule_type_map[bucket] = canonical_rule_types

        if not priority_order:
            return cls()

        residual_bucket = "electives"
        residual_label = "Residual elective / unallocated counted course"

        if "residual_bucket" in df.columns:
            values = [
                str(value).strip()
                for value in df["residual_bucket"].tolist()
                if str(value).strip()
            ]

            if values:
                residual_bucket = values[0]

        if "residual_label" in df.columns:
            values = [
                str(value).strip()
                for value in df["residual_label"].tolist()
                if str(value).strip()
            ]

            if values:
                residual_label = values[0]

        return cls(
            priority_order=priority_order,
            requirement_area_map=requirement_area_map,
            canonical_rule_type_map=canonical_rule_type_map,
            bucket_display_names=bucket_display_names,
            residual_bucket=residual_bucket,
            residual_label=residual_label,
        )
