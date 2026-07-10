# -*- coding: utf-8 -*-
"""
Created on Fri Jul 10 08:25:56 2026

@author: Tim Rodgers w M365 Copilot

Audit engine for the degree audit pipeline.

Coordinates:
- Course classification
- Faculty audit
- Specialization possible-match audit
- Promotion audit
- Course allocation
- Allocated specialization audit
- Output writing
- Concise console summary
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .models import AuditInputBundle
from .models import AuditWorkingData
from .models import AllocationConfig

from .course_classifier import CourseClassifier
from .faculty_auditor import FacultyAuditor
from .specialization_auditor import SpecializationAuditor
from .promotion_auditor import PromotionAuditor
from .allocation_engine import AllocationEngine


class AuditEngine:
    """
    Coordinates a complete audit run for one loaded audit bundle.
    """

    def __init__(
        self,
        bundle: AuditInputBundle,
        allocation_config: AllocationConfig | None = None,
    ):
        self.bundle = bundle
        self.allocation_config = allocation_config

        self.course_classifier = CourseClassifier.from_audit_bundle(
            bundle
        )

        self.faculty_auditor = FacultyAuditor.from_audit_bundle(
            bundle
        )

        self.specialization_auditor = SpecializationAuditor.from_audit_bundle(
            bundle
        )

        self.promotion_auditor = PromotionAuditor.from_audit_bundle(
            bundle
        )

        self.allocation_engine = AllocationEngine.from_audit_bundle(
            bundle,
            allocation_config=allocation_config,
        )

    @classmethod
    def from_bundle(
        cls,
        bundle: AuditInputBundle,
        allocation_config: AllocationConfig | None = None,
    ):
        """
        Build AuditEngine from a loaded AuditInputBundle.
        """

        return cls(
            bundle=bundle,
            allocation_config=allocation_config,
        )

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def run(self) -> AuditWorkingData:
        """
        Run the full audit pipeline.

        Returns
        -------
        AuditWorkingData
            Object containing intermediate and final audit dataframes.
        """

        working = AuditWorkingData(
            bundle=self.bundle
        )

        working.classified_courses = self.course_classifier.classify()

        working.faculty_audit_summary = self.faculty_auditor.audit(
            working.classified_courses
        )

        working.specialization_audit = self.specialization_auditor.audit(
            working.classified_courses
        )

        working.promotion_audit = self.promotion_auditor.audit(
            working.classified_courses
        )

        working.course_allocation = self.allocation_engine.allocate(
            classified_courses=working.classified_courses,
            specialization_audit=working.specialization_audit,
        )

        working.allocated_specialization_audit = (
            self.allocation_engine.build_allocated_specialization_audit(
                course_allocation=working.course_allocation,
                specialization_audit=working.specialization_audit,
            )
        )

        return working

    # ------------------------------------------------------------------
    # Output writing
    # ------------------------------------------------------------------

    def get_output_dir(
        self,
        base_output_dir: str | Path = "audit_outputs",
    ) -> Path:
        """
        Get output directory for this audit case.
        """

        return Path(base_output_dir) / self.bundle.profile.case_id

    def write_outputs(
        self,
        working: AuditWorkingData,
        base_output_dir: str | Path = "audit_outputs",
    ) -> dict:
        """
        Write audit outputs to CSV files.

        Returns
        -------
        dict
            Mapping from output name to output path.
        """

        output_dir = self.get_output_dir(
            base_output_dir=base_output_dir
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        output_paths = {}

        self._write_if_present(
            output_paths=output_paths,
            key="course_classification",
            df=working.classified_courses,
            path=output_dir / "course_classification.csv",
        )

        self._write_if_present(
            output_paths=output_paths,
            key="faculty_audit_summary",
            df=working.faculty_audit_summary,
            path=output_dir / "faculty_audit_summary.csv",
        )

        self._write_if_present(
            output_paths=output_paths,
            key="specialization_audit",
            df=working.specialization_audit,
            path=output_dir / "specialization_audit.csv",
        )

        self._write_if_present(
            output_paths=output_paths,
            key="promotion_audit",
            df=working.promotion_audit,
            path=output_dir / "promotion_audit.csv",
        )

        self._write_if_present(
            output_paths=output_paths,
            key="course_allocation",
            df=working.course_allocation,
            path=output_dir / "course_allocation.csv",
        )

        self._write_if_present(
            output_paths=output_paths,
            key="allocated_specialization_audit",
            df=working.allocated_specialization_audit,
            path=output_dir / "allocated_specialization_audit.csv",
        )

        return output_paths

    @staticmethod
    def _write_if_present(
        output_paths: dict,
        key: str,
        df: pd.DataFrame | None,
        path: Path,
    ) -> None:
        if df is None:
            return

        df.to_csv(
            path,
            index=False
        )

        output_paths[key] = path

    # ------------------------------------------------------------------
    # Concise console summaries
    # ------------------------------------------------------------------

    def print_summary(
        self,
        working: AuditWorkingData,
        max_missing_rows: int = 12,
        max_courses_to_show: int = 3,
    ) -> None:
        """
        Print concise audit summary.

        This is intended for quick command-line inspection.
        """

        self.print_case_header(working)

        self.print_quick_counts(working)

        self.print_faculty_section(
            working=working,
            max_rows=max_missing_rows,
        )

        self.print_specialization_section(
            working=working,
            max_rows=max_missing_rows,
            max_courses_to_show=max_courses_to_show,
        )

        self.print_promotion_target_section(
            working=working,
            max_rows=max_missing_rows,
        )

        self.print_electives_section(
            working=working,
            max_courses_to_show=max_courses_to_show,
        )

        print()

    def print_case_header(
        self,
        working: AuditWorkingData,
    ) -> None:
        profile = self.bundle.profile
        options = self.bundle.options

        print()
        print("Degree Audit")
        print("============")
        print(f"Case ID: {profile.case_id}")
        print(f"Calendar year: {profile.calendar_year}")
        print(f"Program: {profile.program}")
        print(f"Program type: {profile.program_type}")
        print(f"Option ID: {profile.option_id}")
        print(f"Academic year: {profile.academic_year}")
        print(f"Audit mode: {options.audit_mode}")
        print(f"Counted statuses: {options.count_statuses}")

        counted_credits = self._counted_credits(
            working.classified_courses
        )

        print(f"Total counted credits: {self._format_number(counted_credits)}")
        print()

    def print_quick_counts(
        self,
        working: AuditWorkingData,
    ) -> None:
        faculty_satisfied, faculty_total = self._status_counts(
            working.faculty_audit_summary,
            status_column="status",
        )

        spec_satisfied, spec_total = self._status_counts(
            working.allocated_specialization_audit,
            status_column="allocated_status",
        )

        print("Quick Audit Summary")
        print("-------------------")
        print(
            f"Faculty audit: "
            f"{faculty_satisfied}/{faculty_total} specifications satisfied"
        )
        print(
            f"Allocated specialization audit: "
            f"{spec_satisfied}/{spec_total} specifications satisfied"
        )

        target_year = self._promotion_target_year()

        if target_year is not None:
            promotion_rows = self._promotion_rows_for_target(
                working.promotion_audit,
                target_year,
            )

            promotion_satisfied, promotion_total = self._status_counts(
                promotion_rows,
                status_column="status",
            )

            if promotion_total > 0:
                print(
                    f"Promotion to Year {target_year}: "
                    f"{promotion_satisfied}/{promotion_total} specifications satisfied"
                )

        print()

    # ------------------------------------------------------------------
    # Human-readable sections
    # ------------------------------------------------------------------

    def print_faculty_section(
        self,
        working: AuditWorkingData,
        max_rows: int = 12,
    ) -> None:
        print("Faculty")
        print("-------")

        faculty_df = working.faculty_audit_summary

        if faculty_df is None or faculty_df.empty:
            print("Faculty audit was not evaluated.")
            print()
            return

        missing = faculty_df[
            faculty_df["status"].astype(str).str.lower() != "satisfied"
        ].copy()

        if missing.empty:
            print("All requirements satisfied.")
        else:
            satisfied, total = self._status_counts(
                faculty_df,
                status_column="status",
            )

            print(f"{satisfied}/{total} requirements satisfied.")
            print()

            for _, row in missing.head(max_rows).iterrows():
                print(self._describe_faculty_row(row))
                print()

            remaining = len(missing) - max_rows

            if remaining > 0:
                print(f"... {remaining} additional Faculty requirement(s) not shown.")

        self._print_other_faculty_credit_capacity(faculty_df)

        print()

    def print_specialization_section(
        self,
        working: AuditWorkingData,
        max_rows: int = 12,
        max_courses_to_show: int = 3,
    ) -> None:
        print("Specialization")
        print("--------------")

        allocated_df = working.allocated_specialization_audit

        if allocated_df is None or allocated_df.empty:
            print("Allocated specialization audit was not evaluated.")
            print()
            return

        status_column = (
            "allocated_status"
            if "allocated_status" in allocated_df.columns
            else "status"
        )

        missing = allocated_df[
            allocated_df[status_column].astype(str).str.lower() != "satisfied"
        ].copy()

        if missing.empty:
            print("All requirements satisfied.")
        else:
            satisfied, total = self._status_counts(
                allocated_df,
                status_column=status_column,
            )

            print(f"{satisfied}/{total} requirements satisfied.")
            print()

            for _, row in missing.head(max_rows).iterrows():
                print(
                    self._describe_allocated_specialization_row(
                        row=row,
                        status_column=status_column,
                        max_courses_to_show=max_courses_to_show,
                    )
                )
                print()

            remaining = len(missing) - max_rows

            if remaining > 0:
                print(
                    f"... {remaining} additional specialization requirement(s) not shown."
                )

        print()

    def print_promotion_target_section(
        self,
        working: AuditWorkingData,
        max_rows: int = 12,
    ) -> None:
        target_year = self._promotion_target_year()

        if target_year is None:
            print("Promotion")
            print("---------")
            print("Promotion target is unknown because academic_year is missing.")
            print()
            return

        print(f"Promotion to Year {target_year}")
        print("-------------------")

        rows = self._promotion_rows_for_target(
            working.promotion_audit,
            target_year,
        )

        if rows.empty:
            print("Promotion requirements were not evaluated.")
            print()
            return

        missing = rows[
            rows["status"].astype(str).str.lower() != "satisfied"
        ].copy()

        if missing.empty:
            print("All requirements satisfied.")
        else:
            satisfied, total = self._status_counts(
                rows,
                status_column="status",
            )

            print(f"{satisfied}/{total} requirements satisfied.")
            print()

            for _, row in missing.head(max_rows).iterrows():
                print(self._describe_promotion_row(row))
                print()

            remaining = len(missing) - max_rows

            if remaining > 0:
                print(f"... {remaining} additional promotion requirement(s) not shown.")

        print()

    def print_electives_section(
        self,
        working: AuditWorkingData,
        max_courses_to_show: int = 3,
    ) -> None:
        print("Electives / Allocation")
        print("----------------------")

        allocation = working.course_allocation

        if allocation is None or allocation.empty:
            print("Course allocation was not evaluated.")
            print()
            return

        electives = allocation[
            allocation["exclusive_bucket"].astype(str).str.strip()
            == "electives"
        ].copy()

        elective_credits = float(electives["credits"].sum()) if not electives.empty else 0

        print(
            f"You have {self._format_number(elective_credits)} credits "
            "allocated as free/residual electives under this plan."
        )

        if not electives.empty:
            elective_courses = ";".join(
                electives["effective_course_code"]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .tolist()
            )

            limited_courses = self._limited_course_list(
                elective_courses,
                max_courses=max_courses_to_show,
            )

            if limited_courses:
                print(f"Example elective courses: {limited_courses}")

        print(
            "These credits still count toward total degree credits, "
            "subject to Faculty limits."
        )

        self._print_other_faculty_elective_capacity(
            working=working
        )

        print()

    # ------------------------------------------------------------------
    # Row description helpers
    # ------------------------------------------------------------------

    def _describe_faculty_row(
        self,
        row,
    ) -> str:
        requirement_id = row.get("requirement_id", "Faculty requirement")
        status = row.get("status", "")
        completed = row.get("completed", "")
        required = row.get("required", "")
        remaining = row.get("remaining", "")
        unit = row.get("unit", "")
        notes = row.get("notes", "")

        lines = [
            f"{requirement_id}: {status}",
            (
                f"  Progress: {self._format_number(completed)} / "
                f"{self._format_number(required)} {unit}; "
                f"remaining: {self._format_number(remaining)} {unit}"
            ),
        ]

        if str(requirement_id).upper() == "TOTAL_CREDITS":
            lines.append(
                f"  Require {self._format_number(remaining)} more credits to graduate."
            )

        if notes:
            lines.append(f"  Notes: {notes}")

        return "\n".join(lines)

    def _describe_allocated_specialization_row(
        self,
        row,
        status_column: str,
        max_courses_to_show: int,
    ) -> str:
        group_id = row.get("group_id", "Specialization requirement")
        status = row.get(status_column, "")
        label = row.get("label", "")
        area = row.get("requirement_area", "")

        completed = row.get("allocated_completed", row.get("completed", ""))
        required = row.get("allocated_required", row.get("required", ""))
        remaining = row.get("allocated_remaining", row.get("remaining", ""))
        unit = row.get("allocated_unit", row.get("unit", ""))

        allocated_courses = row.get(
            "allocated_courses",
            row.get("matched_courses", "")
        )

        allocation_notes = row.get(
            "allocation_notes",
            row.get("notes", "")
        )

        lines = [
            f"{group_id}: {status}",
        ]

        if area:
            lines.append(f"  Area: {area}")

        if label:
            lines.append(f"  Label: {label}")

        if unit:
            lines.append(
                f"  Progress: {self._format_number(completed)} / "
                f"{self._format_number(required)} {unit}; "
                f"remaining: {self._format_number(remaining)} {unit}"
            )

        limited_courses = self._limited_course_list(
            allocated_courses,
            max_courses=max_courses_to_show,
        )

        if limited_courses:
            lines.append(f"  Allocated courses: {limited_courses}")

        if allocation_notes:
            lines.append(f"  Notes: {allocation_notes}")

        return "\n".join(lines)

    def _describe_promotion_row(
        self,
        row,
    ) -> str:
        rule_id = row.get("rule_id", "Promotion requirement")
        status = row.get("status", "")
        completed = row.get("completed", "")
        required = row.get("required", "")
        remaining = row.get("remaining", "")
        unit = row.get("unit", "")
        notes = row.get("notes", "")

        lines = [
            f"{rule_id}: {status}",
            (
                f"  Progress: {self._format_number(completed)} / "
                f"{self._format_number(required)} {unit}; "
                f"remaining: {self._format_number(remaining)} {unit}"
            ),
        ]

        if notes:
            lines.append(f"  Notes: {notes}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Other-faculty / non-Arts non-Science helpers
    # ------------------------------------------------------------------

    def _print_other_faculty_credit_capacity(
        self,
        faculty_df: pd.DataFrame,
    ) -> None:
        cap_row = self._get_other_faculty_cap_row(faculty_df)

        if cap_row is None:
            return

        completed = cap_row.get("completed", 0)
        maximum = cap_row.get("required", 0)
        remaining_capacity = cap_row.get("remaining", 0)
        surplus = cap_row.get("surplus", 0)
        status = str(cap_row.get("status", "")).strip().lower()
        unit = cap_row.get("unit", "credits")

        print()
        print("Other-faculty credit capacity:")

        if status == "exceeds_limit":
            print(
                f"You have {self._format_number(completed)} / "
                f"{self._format_number(maximum)} {unit} from courses that are "
                "neither Science nor Arts."
            )
            print(
                f"You are over the current limit by "
                f"{self._format_number(surplus)} {unit}."
            )
        else:
            print(
                f"You have {self._format_number(completed)} / "
                f"{self._format_number(maximum)} {unit} from courses that are "
                "neither Science nor Arts."
            )
            print(
                f"You can take up to "
                f"{self._format_number(remaining_capacity)} more {unit} "
                "outside Science and Arts under the current Faculty cap."
            )

    def _print_other_faculty_elective_capacity(
        self,
        working: AuditWorkingData,
    ) -> None:
        faculty_df = working.faculty_audit_summary

        if faculty_df is None or faculty_df.empty:
            return

        cap_row = self._get_other_faculty_cap_row(faculty_df)

        if cap_row is None:
            return

        remaining_capacity = cap_row.get("remaining", 0)
        surplus = cap_row.get("surplus", 0)
        status = str(cap_row.get("status", "")).strip().lower()
        unit = cap_row.get("unit", "credits")

        if status == "exceeds_limit":
            print(
                f"Non-Arts/non-Science cap exceeded by "
                f"{self._format_number(surplus)} {unit}."
            )
        else:
            print(
                f"Remaining non-Arts/non-Science capacity: "
                f"{self._format_number(remaining_capacity)} {unit}."
            )

    @staticmethod
    def _get_other_faculty_cap_row(
        faculty_df: pd.DataFrame,
    ):
        if faculty_df is None or faculty_df.empty:
            return None

        if "requirement_id" not in faculty_df.columns:
            return None

        rows = faculty_df[
            faculty_df["requirement_id"]
            .astype(str)
            .str.upper()
            == "OTHER_FACULTY_CREDITS_CAP"
        ]

        if rows.empty:
            return None

        return rows.iloc[0]

    # ------------------------------------------------------------------
    # Summary calculation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _status_counts(
        df: pd.DataFrame | None,
        status_column: str,
    ) -> tuple[int, int]:
        if df is None or df.empty:
            return 0, 0

        if status_column not in df.columns:
            return 0, len(df)

        statuses = df[status_column].astype(str).str.lower()

        satisfied = statuses.eq("satisfied").sum()
        total = len(df)

        return int(satisfied), int(total)

    def _promotion_target_year(self) -> int | None:
        academic_year = self.bundle.profile.academic_year

        if academic_year is None:
            return None

        return int(academic_year) + 1

    @staticmethod
    def _promotion_rows_for_target(
        promotion_df: pd.DataFrame | None,
        target_year: int,
    ) -> pd.DataFrame:
        if promotion_df is None or promotion_df.empty:
            return pd.DataFrame()

        return promotion_df[
            promotion_df["promotion_to"].astype(str) == str(target_year)
        ].copy()

    def _counted_credits(
        self,
        classified_courses: pd.DataFrame | None,
    ) -> float:
        if classified_courses is None or classified_courses.empty:
            return 0

        statuses = {
            status.strip().lower()
            for status in self.bundle.options.count_statuses
        }

        excluded = {
            "failed",
            "withdrawn",
            "w",
            "fail",
        }

        df = classified_courses.copy()

        normalized = df["status"].astype(str).str.strip().str.lower()

        counted = df[
            normalized.isin(statuses)
            & ~normalized.isin(excluded)
        ].copy()

        return float(counted["credits"].sum())

    @staticmethod
    def _format_number(value) -> str:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return str(value)

        if value.is_integer():
            return str(int(value))

        return f"{value:.1f}"

    @staticmethod
    def _limited_course_list(
        course_string,
        max_courses: int,
    ) -> str:
        if course_string is None:
            return ""

        courses = [
            item.strip()
            for item in str(course_string).split(";")
            if item.strip()
        ]

        if not courses:
            return ""

        shown = courses[:max_courses]
        remaining = len(courses) - len(shown)

        text = ";".join(shown)

        if remaining > 0:
            text = f"{text}; ... +{remaining} more"

        return text