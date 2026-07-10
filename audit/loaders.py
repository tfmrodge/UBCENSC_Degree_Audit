# -*- coding: utf-8 -*-
"""
Created on Tue Jul  7 15:41:38 2026

@author: Tim Rodgers w M365 CoPilot
CSV loaders for the UBC ENSC degree audit engine.
"""

# -*- coding: utf-8 -*-
"""
Generic CSV loaders for the degree audit pipeline.

This module is intentionally mostly program-agnostic.
Convenience functions at the bottom can be used for ENSC-specific tests.
"""

from pathlib import Path
from typing import Optional

import pandas as pd

from .models import (
    AuditInputBundle,
    AuditOptions,
    FacultyRequirementData,
    SpecializationRequirementData,
    StudentCourseData,
    StudentProfile,
)


class DegreeAuditLoader:
    """
    Generic file loader for degree audit data.

    This class knows how to load:
    - student_profile.csv
    - student_courses.csv
    - requirement_groups.csv
    - requirement_courses.csv
    - faculty requirement CSV files

    It does not perform the audit.
    """

    def __init__(self, root_dir: str | Path = "."):
        self.root_dir = Path(root_dir)

    # ------------------------------------------------------------------
    # High-level loading
    # ------------------------------------------------------------------

    def load_audit_bundle(
        self,
        student_profile_path: str | Path,
        student_courses_path: str | Path,
        requirement_dir: str | Path,
        faculty_requirement_dir: str | Path,
        options: Optional[AuditOptions] = None,
    ) -> AuditInputBundle:
        """
        Load a complete audit input bundle from explicit paths.
        """

        if options is None:
            options = AuditOptions()

        profile = self.load_student_profile(student_profile_path)

        student_courses = self.load_student_courses(student_courses_path)

        specialization_requirements = self.load_requirement_data(requirement_dir)

        faculty_requirements = self.load_faculty_requirement_data(
            faculty_requirement_dir
        )

        return AuditInputBundle(
            profile=profile,
            student_courses=student_courses,
            specialization_requirements=specialization_requirements,
            faculty_requirements=faculty_requirements,
            options=options,
        )

    def load_student_case_folder(
        self,
        student_case_dir: str | Path,
        requirement_dir: str | Path,
        faculty_requirement_dir: str | Path,
        options: Optional[AuditOptions] = None,
    ) -> AuditInputBundle:
        """
        Load a student case from a folder.

        Expected:
            student_case_dir/student_profile.csv
            student_case_dir/student_courses.csv
        """

        student_case_dir = Path(student_case_dir)

        return self.load_audit_bundle(
            student_profile_path=student_case_dir / "student_profile.csv",
            student_courses_path=student_case_dir / "student_courses.csv",
            requirement_dir=requirement_dir,
            faculty_requirement_dir=faculty_requirement_dir,
            options=options,
        )

    # ------------------------------------------------------------------
    # Student inputs
    # ------------------------------------------------------------------

    def load_student_profile(
        self,
        path: str | Path,
    ) -> StudentProfile:
        """
        Load student_profile.csv.

        Expected format:
            field,value,notes
        """

        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Missing student profile: {path}")

        df = pd.read_csv(path, dtype=str).fillna("")

        required_columns = {"field", "value"}
        missing = required_columns - set(df.columns)

        if missing:
            raise ValueError(
                f"{path} is missing required columns: {sorted(missing)}"
            )

        profile_dict = {}

        for _, row in df.iterrows():
            field = str(row["field"]).strip()
            value = str(row["value"]).strip()

            if field:
                profile_dict[field] = value

        profile = StudentProfile(
            case_id=profile_dict.get("case_id", "unknown_case"),
            calendar_year=profile_dict.get("calendar_year", ""),
            program=profile_dict.get("program", ""),
            program_type=profile_dict.get("program_type", ""),
            option_id=self.blank_to_none(profile_dict.get("option_id", "")),
            academic_year=self.to_optional_int(
                profile_dict.get("academic_year", "")
            ),
            start_date=self.blank_to_none(profile_dict.get("start_date", "")),
            has_biology_12=self.to_optional_bool(
                profile_dict.get("has_biology_12", "")
            ),
            has_chemistry_12=self.to_optional_bool(
                profile_dict.get("has_chemistry_12", "")
            ),
            has_physics_12=self.to_optional_bool(
                profile_dict.get("has_physics_12", "")
            ),
            raw=profile_dict,
        )

        self.validate_student_profile(profile)

        return profile

    def load_student_courses(
        self,
        path: str | Path,
    ) -> StudentCourseData:
        """
        Load and normalize student_courses.csv.
        """

        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Missing student courses: {path}")

        df = pd.read_csv(path, dtype=str).fillna("")

        required_columns = {
            "course_code",
            "status",
            "credits",
        }

        missing = required_columns - set(df.columns)

        if missing:
            raise ValueError(
                f"{path} is missing required columns: {sorted(missing)}"
            )

        optional_columns = [
            "term",
            "year_taken",
            "grade",
            "percentage",
            "source",
            "override_exclusive_group_id",
            "override_exclusive_requirement_area",
            "override_allow_double_count",
            "override_double_count_groups",
        ]

        for column in optional_columns:
            if column not in df.columns:
                df[column] = ""

        df["course_code"] = df["course_code"].astype(str).str.strip()
        df["override_course_code"] = (
            df["override_course_code"].astype(str).str.strip()
        )

        df["original_course_code"] = df["course_code"].apply(
            self.normalize_course_code
        )

        df["override_course_code_normalized"] = df[
            "override_course_code"
        ].apply(self.normalize_course_code)

        df["effective_course_code"] = df.apply(
            self.get_effective_course_code,
            axis=1,
        )

        df["status"] = df["status"].astype(str).str.strip().str.lower()

        df["credits"] = pd.to_numeric(
            df["credits"],
            errors="coerce",
        )

        df["percentage"] = pd.to_numeric(
            df["percentage"],
            errors="coerce",
        )

        df["year_taken"] = pd.to_numeric(
            df["year_taken"],
            errors="coerce",
        )

        df["subject"] = df["effective_course_code"].apply(
            self.extract_subject
        )

        df["course_number"] = df["effective_course_code"].apply(
            self.extract_course_number
        )

        df["course_level"] = df["course_number"].apply(
            self.extract_course_level
        )

        self.validate_student_courses(df)

        return StudentCourseData(
            courses=df,
            source_path=path,
        )

    # ------------------------------------------------------------------
    # Requirement data
    # ------------------------------------------------------------------

    def load_requirement_data(
        self,
        requirement_dir: str | Path,
    ) -> SpecializationRequirementData:
        """
        Load requirement_groups.csv and requirement_courses.csv from a directory.
        """

        requirement_dir = Path(requirement_dir)

        groups_path = requirement_dir / "requirement_groups.csv"
        courses_path = requirement_dir / "requirement_courses.csv"
        allocation_config_path = requirement_dir / "allocation_config.csv"

        if not groups_path.exists():
            raise FileNotFoundError(
                f"Missing requirement_groups.csv: {groups_path}"
            )

        if not courses_path.exists():
            raise FileNotFoundError(
                f"Missing requirement_courses.csv: {courses_path}"
            )
            

        requirement_groups = pd.read_csv(
            groups_path,
            dtype=str,
        ).fillna("")

        requirement_courses = pd.read_csv(
            courses_path,
            dtype=str,
        ).fillna("")
        
        allocation_config = None
        
        if allocation_config_path.exists():
            allocation_config = pd.read_csv(
                allocation_config_path,
                dtype=str
            ).fillna("")

        requirement_groups = self.normalize_requirement_groups(
            requirement_groups
        )

        requirement_courses = self.normalize_requirement_courses(
            requirement_courses
        )

        return SpecializationRequirementData(
            requirement_groups=requirement_groups,
            requirement_courses=requirement_courses,
            source_dir=requirement_dir,
            allocation_config=allocation_config
        )

    def load_faculty_requirement_data(
        self,
        faculty_requirement_dir: str | Path,
    ) -> FacultyRequirementData:
        """
        Load all CSV files from a faculty requirement directory.
        """

        faculty_requirement_dir = Path(faculty_requirement_dir)

        files = {}

        if not faculty_requirement_dir.exists():
            raise FileNotFoundError(
                f"Missing faculty requirement directory: {faculty_requirement_dir}"
            )

        for path in sorted(faculty_requirement_dir.glob("*.csv")):
            files[path.stem] = pd.read_csv(
                path,
                dtype=str,
            ).fillna("")

        return FacultyRequirementData(
            files=files,
            source_dir=faculty_requirement_dir,
        )

    # ------------------------------------------------------------------
    # Requirement normalization
    # ------------------------------------------------------------------

    def normalize_requirement_groups(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        df = df.copy()

        numeric_columns = [
            "credits",
            "rule_value",
        ]

        for column in numeric_columns:
            if column in df.columns:
                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

        expected_columns = [
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
            "source_text",
        ]

        for column in expected_columns:
            if column not in df.columns:
                df[column] = ""

        return df

    def normalize_requirement_courses(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        df = df.copy()

        if "course_code" in df.columns:
            df["course_code"] = df["course_code"].apply(
                self.normalize_course_code_or_wildcard
            )

        numeric_columns = [
            "credits",
            "rule_value",
        ]

        for column in numeric_columns:
            if column in df.columns:
                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

        expected_columns = [
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
            "course_code",
            "rule_subject",
            "include_pattern",
            "exclude_pattern",
            "rule_unit",
            "source_text",
        ]

        for column in expected_columns:
            if column not in df.columns:
                df[column] = ""

        return df

    # ------------------------------------------------------------------
    # Course-code helpers
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_course_code(value) -> str:
        """
        Normalize course strings.

        Examples:
            ENVR 100 -> ENVR100
            ENVR_V 100 -> ENVR100
            CHEM_V 121 - Structure and Bonding -> CHEM121
        """

        if value is None:
            return ""

        text = str(value).strip().upper()

        if not text:
            return ""

        import re

        match = re.search(
            r"\b([A-Z]{2,5})_?V?\s*[-_]?\s*(\d{3}[A-Z]?)\b",
            text,
        )

        if not match:
            return ""

        subject = match.group(1)
        number = match.group(2)

        return f"{subject}{number}"

    @staticmethod
    def normalize_course_code_or_wildcard(value) -> str:
        """
        Normalize course codes but preserve wildcard rows like HGSE*.
        """

        if value is None:
            return ""

        text = str(value).strip().upper()

        if not text:
            return ""

        if text.endswith("*"):
            return text

        return DegreeAuditLoader.normalize_course_code(text)

    @staticmethod
    def get_effective_course_code(row) -> str:
        override = row.get("override_course_code_normalized", "")

        if override:
            return override

        return row.get("original_course_code", "")

    @staticmethod
    def extract_subject(course_code: str) -> str:
        import re

        match = re.match(
            r"^([A-Z]{2,5})",
            str(course_code),
        )

        if not match:
            return ""

        return match.group(1)

    @staticmethod
    def extract_course_number(course_code: str) -> Optional:
        import re

        match = re.search(
            r"(\d{3})",
            str(course_code),
        )

        if not match:
            return None

        return int(match.group(1))

    @staticmethod
    def extract_course_level(course_number: Optional[int]) -> Optional:
        if course_number is None:
            return None

        return int(course_number // 100 * 100)

    # ------------------------------------------------------------------
    # Folder helpers
    # ------------------------------------------------------------------

    @staticmethod
    def make_requirement_folder_name(
        program: str,
        calendar_year: str,
    ) -> str:
        program_part = program.strip().lower()

        year_part = (
            calendar_year
            .strip()
            .replace("-", "_")
            .replace("/", "_")
        )

        return f"{program_part}_{year_part}"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_student_profile(
        profile: StudentProfile,
    ) -> None:
        missing = []

        if not profile.case_id:
            missing.append("case_id")

        if not profile.calendar_year:
            missing.append("calendar_year")

        if not profile.program:
            missing.append("program")

        if not profile.program_type:
            missing.append("program_type")

        if missing:
            raise ValueError(
                f"student_profile.csv is missing required values: {missing}"
            )

    @staticmethod
    def validate_student_courses(
        df: pd.DataFrame,
    ) -> None:
        if df.empty:
            raise ValueError("student_courses.csv has no course rows.")

        invalid_courses = df[df["effective_course_code"].eq("")]

        if not invalid_courses.empty:
            raise ValueError(
                "Some student courses could not be normalized: "
                f"{invalid_courses[['course_code', 'override_course_code']].to_dict('records')}"
            )

        invalid_credits = df[df["credits"].isna()]

        if not invalid_credits.empty:
            raise ValueError(
                "Some student courses have invalid credits: "
                f"{invalid_credits[['course_code', 'credits']].to_dict('records')}"
            )

    # ------------------------------------------------------------------
    # Scalar conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def blank_to_none(value) -> Optional:
        value = str(value).strip()

        if value == "":
            return None

        return value

    @staticmethod
    def to_optional_int(value) -> Optional:
        value = str(value).strip()

        if value == "":
            return None

        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def to_optional_bool(value) -> Optional:
        value = str(value).strip().lower()

        if value == "":
            return None

        if value in {"true", "yes", "y", "1"}:
            return True

        if value in {"false", "no", "n", "0"}:
            return False

        return None


# ----------------------------------------------------------------------
# Convenience function for current ENSC project/testing
# ----------------------------------------------------------------------

def load_ensc_audit_case(
    student_case_dir: str | Path,
    root_dir: str | Path = ".",
    options: Optional[AuditOptions] = None,
) -> AuditInputBundle:
    """
    Convenience loader for the current ENSC project structure.

    Expected folder structure:
        course_requirements/ensc_2026_2027/
        faculty_requirements/
        student_inputs/example_student_001/
    """

    root_dir = Path(root_dir)

    loader = DegreeAuditLoader(
        root_dir=root_dir
    )

    profile = loader.load_student_profile(
        Path(student_case_dir) / "student_profile.csv"
    )

    requirement_folder = loader.make_requirement_folder_name(
        program=profile.program,
        calendar_year=profile.calendar_year,
    )

    requirement_dir = (
        root_dir
        / "course_requirements"
        / requirement_folder
    )

    faculty_requirement_dir = (
        root_dir
        / "faculty_requirements"
    )

    return loader.load_student_case_folder(
        student_case_dir=student_case_dir,
        requirement_dir=requirement_dir,
        faculty_requirement_dir=faculty_requirement_dir,
        options=options,
    )