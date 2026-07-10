# -*- coding: utf-8 -*-
"""
Created on Thu Jul  9 11:14:58 2026

@author: Tim Rodgers w M365 Copilot

Promotion auditor for the degree audit pipeline.

Checks promotion requirements from:
- promotion_rules.csv

Uses classified course data from CourseClassifier:
- is_science_credit
- is_upper_level
- is_lab_course
- is_communication_course
- course_number
- credits
- status
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


class PromotionAuditor:
    """
    Audits Faculty of Science promotion requirements.
    """

    def __init__(
        self,
        promotion_rules: pd.DataFrame,
        profile,
        options,
    ):
        self.promotion_rules = promotion_rules.copy().fillna("")
        self.profile = profile
        self.options = options

        self._normalize_inputs()

    @classmethod
    def from_audit_bundle(cls, bundle):
        """
        Build a PromotionAuditor from an AuditInputBundle.
        """

        faculty_files = bundle.faculty_requirements.files

        if "promotion_rules" not in faculty_files:
            raise KeyError(
                "Missing promotion_rules.csv in faculty_requirements."
            )

        return cls(
            promotion_rules=faculty_files["promotion_rules"],
            profile=bundle.profile,
            options=bundle.options,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def audit(
        self,
        classified_courses: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Run promotion audit.

        Returns
        -------
        pd.DataFrame
            One row per promotion rule.
        """

        counted_courses = self._filter_counted_courses(
            classified_courses
        )

        rows = []

        for _, rule in self.promotion_rules.iterrows():
            rule_type = str(rule.get("rule_type", "")).strip()

            if rule_type == "min_total_credits":
                rows.append(
                    self._audit_min_total_credits(
                        rule=rule,
                        courses=counted_courses
                    )
                )

            elif rule_type == "min_science_credits":
                rows.append(
                    self._audit_min_science_credits(
                        rule=rule,
                        courses=counted_courses
                    )
                )

            elif rule_type == "min_science_credits_at_level":
                rows.append(
                    self._audit_min_science_credits_at_level(
                        rule=rule,
                        courses=counted_courses
                    )
                )

            elif rule_type == "min_science_credits_at_or_above_level":
                rows.append(
                    self._audit_min_science_credits_at_or_above_level(
                        rule=rule,
                        courses=counted_courses
                    )
                )

            elif rule_type == "min_upper_level_credits":
                rows.append(
                    self._audit_min_upper_level_credits(
                        rule=rule,
                        courses=counted_courses
                    )
                )

            elif rule_type == "one_lab_course":
                rows.append(
                    self._audit_one_lab_course(
                        rule=rule,
                        courses=counted_courses
                    )
                )
            
            elif rule_type == "min_communication_credits":
                rows.append(
                    self._audit_min_communication_credits(
                        rule=rule,
                        courses=counted_courses
                    )
                )

            else:
                rows.append(
                    self._make_summary_row(
                        rule=rule,
                        status="review",
                        completed=0,
                        required=self._rule_value(rule),
                        remaining=self._rule_value(rule),
                        surplus=0,
                        unit=str(rule.get("unit", "")),
                        matched_courses="",
                        notes=(
                            f"Rule type '{rule_type}' is not yet audited "
                            "by PromotionAuditor."
                        )
                    )
                )

        return pd.DataFrame(rows)

    def print_summary(
        self,
        promotion_audit: pd.DataFrame
    ) -> None:
        """
        Print readable terminal summary grouped by promotion year.
        """

        print()
        print("Promotion Audit")
        print("===============")

        if promotion_audit.empty:
            print("No promotion requirements audited.")
            print()
            return

        for promotion_to, group in promotion_audit.groupby("promotion_to"):
            statuses = (
                group["status"]
                .astype(str)
                .str.lower()
                .tolist()
            )

            if all(status == "satisfied" for status in statuses):
                year_status = "satisfied"
            elif any(status == "satisfied" for status in statuses):
                year_status = "partial"
            else:
                year_status = "missing"

            print()
            print(f"Promotion to Year {promotion_to}: {year_status}")
            print("-" * 32)

            for _, row in group.iterrows():
                rule_id = row.get("rule_id", "")
                status = row.get("status", "")
                completed = row.get("completed", "")
                required = row.get("required", "")
                remaining = row.get("remaining", "")
                unit = row.get("unit", "")
                notes = row.get("notes", "")

                print(
                    f"{rule_id}: {status} "
                    f"({completed}/{required} {unit}; "
                    f"remaining: {remaining})"
                )

                if notes:
                    print(f"  Notes: {notes}")

        print()

    def write_summary(
        self,
        promotion_audit: pd.DataFrame,
        output_dir: str | Path,
        filename: str = "promotion_audit.csv"
    ) -> Path:
        """
        Write promotion audit to CSV.
        """

        output_dir = Path(output_dir)

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        output_path = output_dir / filename

        promotion_audit.to_csv(
            output_path,
            index=False
        )

        return output_path

    # ------------------------------------------------------------------
    # Individual rule audits
    # ------------------------------------------------------------------

    def _audit_min_total_credits(
        self,
        rule: pd.Series,
        courses: pd.DataFrame
    ) -> dict:
        matched = courses.copy()

        completed = matched["credits"].sum()
        required = self._rule_value(rule)

        return self._make_summary_row_from_values(
            rule=rule,
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes=str(rule.get("notes", ""))
        )

    def _audit_min_science_credits(
        self,
        rule: pd.Series,
        courses: pd.DataFrame
    ) -> dict:
        matched = courses[
            courses["is_science_credit"] == True
        ].copy()

        completed = matched["credits"].sum()
        required = self._rule_value(rule)

        return self._make_summary_row_from_values(
            rule=rule,
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes=str(rule.get("notes", ""))
        )

    def _audit_min_science_credits_at_level(
        self,
        rule: pd.Series,
        courses: pd.DataFrame
    ) -> dict:
        level_min = self._rule_level_min(rule)
        level_max = self._rule_level_max(rule)

        matched = courses[
            (courses["is_science_credit"] == True)
            &
            (
                pd.to_numeric(
                    courses["course_number"],
                    errors="coerce"
                ).between(level_min, level_max)
            )
        ].copy()

        completed = matched["credits"].sum()
        required = self._rule_value(rule)

        return self._make_summary_row_from_values(
            rule=rule,
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes=str(rule.get("notes", ""))
        )

    def _audit_min_science_credits_at_or_above_level(
        self,
        rule: pd.Series,
        courses: pd.DataFrame
    ) -> dict:
        level_min = self._rule_level_min(rule)
        level_max = self._rule_level_max(rule)

        matched = courses[
            (courses["is_science_credit"] == True)
            &
            (
                pd.to_numeric(
                    courses["course_number"],
                    errors="coerce"
                ).between(level_min, level_max)
            )
        ].copy()

        completed = matched["credits"].sum()
        required = self._rule_value(rule)

        return self._make_summary_row_from_values(
            rule=rule,
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes=str(rule.get("notes", ""))
        )

    def _audit_min_upper_level_credits(
        self,
        rule: pd.Series,
        courses: pd.DataFrame
    ) -> dict:
        level_min = self._rule_level_min(rule)
        level_max = self._rule_level_max(rule)

        matched = courses[
            pd.to_numeric(
                courses["course_number"],
                errors="coerce"
            ).between(level_min, level_max)
        ].copy()

        completed = matched["credits"].sum()
        required = self._rule_value(rule)

        return self._make_summary_row_from_values(
            rule=rule,
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes=str(rule.get("notes", ""))
        )
    def _audit_one_lab_course(
        self,
        rule: pd.Series,
        courses: pd.DataFrame
    ) -> dict:
        """
        Audit Laboratory Science Requirement for promotion.
    
        Counts distinct eligible lab courses.
        """
    
        matched = courses[
            courses["is_lab_course"] == True
        ].copy()
    
        completed = (
            matched["effective_course_code"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .shape[0]
        )
    
        required = self._rule_value(rule)
    
        return self._make_summary_row_from_values(
            rule=rule,
            completed=completed,
            required=required,
            unit="course",
            matched_courses=self._course_list(matched),
            notes=str(rule.get("notes", ""))
        )
    
    def _audit_min_communication_credits(
        self,
        rule: pd.Series,
        courses: pd.DataFrame
    ) -> dict:
        """
        Audit Communication Requirement for promotion.
    
        Counts credits from courses tagged as communication courses.
        """
    
        matched = courses[
            courses["is_communication_course"] == True
        ].copy()
    
        completed = matched["credits"].sum()
        required = self._rule_value(rule)
    
        return self._make_summary_row_from_values(
            rule=rule,
            completed=completed,
            required=required,
            unit="credits",
            matched_courses=self._course_list(matched),
            notes=str(rule.get("notes", ""))
        )

    # ------------------------------------------------------------------
    # Summary row helpers
    # ------------------------------------------------------------------

    def _make_summary_row_from_values(
        self,
        rule: pd.Series,
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

        if required_value == 0:
            status = "review"

        elif completed_value >= required_value:
            status = "satisfied"

        elif completed_value > 0:
            status = "partial"

        else:
            status = "missing"

        return self._make_summary_row(
            rule=rule,
            status=status,
            completed=completed_value,
            required=required_value,
            remaining=remaining_value,
            surplus=surplus_value,
            unit=unit,
            matched_courses=matched_courses,
            notes=notes
        )

    @staticmethod
    def _make_summary_row(
        rule: pd.Series,
        status: str,
        completed,
        required,
        remaining,
        surplus,
        unit: str,
        matched_courses: str,
        notes: str
    ) -> dict:
        return {
            "promotion_to": rule.get("promotion_to", ""),
            "rule_id": rule.get("rule_id", ""),
            "requirement_area": rule.get("requirement_area", ""),
            "rule_type": rule.get("rule_type", ""),
            "status": status,
            "completed": completed,
            "required": required,
            "remaining": remaining,
            "surplus": surplus,
            "unit": unit,
            "matched_courses": matched_courses,
            "notes": notes,
        }

    # ------------------------------------------------------------------
    # Helpers
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
    def _rule_value(
        rule: pd.Series
    ) -> float:
        value = rule.get("value", 0)

        if pd.isna(value) or value == "":
            return 0

        return float(value)

    @staticmethod
    def _rule_level_min(
        rule: pd.Series
    ) -> float:
        value = rule.get("course_level_min", "")

        if pd.isna(value) or value == "":
            return 0

        return float(value)

    @staticmethod
    def _rule_level_max(
        rule: pd.Series
    ) -> float:
        value = rule.get("course_level_max", "")

        if pd.isna(value) or value == "":
            return 999

        return float(value)

    def _normalize_inputs(self) -> None:
        expected_columns = [
            "promotion_to",
            "rule_id",
            "requirement_area",
            "rule_type",
            "value",
            "unit",
            "course_level_min",
            "course_level_max",
            "science_only",
            "notes",
        ]

        for column in expected_columns:
            if column not in self.promotion_rules.columns:
                self.promotion_rules[column] = ""

        numeric_columns = [
            "promotion_to",
            "value",
            "course_level_min",
            "course_level_max",
        ]

        for column in numeric_columns:
            self.promotion_rules[column] = pd.to_numeric(
                self.promotion_rules[column],
                errors="coerce"
            )

