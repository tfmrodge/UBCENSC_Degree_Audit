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
class RequirementData:
    """
    Requirement groups and requirement courses for a calendar/program package.
    """

    requirement_groups: pd.DataFrame
    requirement_courses: pd.DataFrame
    source_dir: Path


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
    requirements: RequirementData
    faculty_requirements: FacultyRequirementData
    options: AuditOptions