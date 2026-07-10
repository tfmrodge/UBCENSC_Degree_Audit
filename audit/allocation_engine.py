# -*- coding: utf-8 -*-
"""
Created on Thu Jul  9 12:08:11 2026

@author: Tim Rodgers w M365 Copilot

Allocation engine for the degree audit pipeline.

This module answers:
- What exclusive requirement bucket is each course assigned to?
- After exclusive allocation, which specialization requirements are satisfied?

This is intentionally separate from SpecializationAuditor.

SpecializationAuditor:
    Non-exclusive possible matching.

AllocationEngine:
    Exclusive assignment and post-allocation specialization audit.

"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .models import AllocationConfig
from .specialization_requirement_resolver import SpecializationRequirementResolver


class AllocationEngine:
    """
    Deterministic greedy allocation engine.

    The allocation engine uses AllocationConfig to map program-specific
    requirement_area names into generic buckets such as:
    - core
    - tools
    - option
    - complementary
    - electives
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
        self.config = allocation_config or AllocationConfig()
        
        self.resolver = SpecializationRequirementResolver(
            requirement_groups=requirement_groups,
            requirement_courses=requirement_courses,
            profile=profile,
            allocation_config=self.config,
        )
        
        self.requirement_groups = self.resolver.requirement_groups
        self.requirement_courses = self.resolver.requirement_courses

    @classmethod
    def from_audit_bundle(
        cls,
        bundle,
        allocation_config: AllocationConfig | None = None,
    ):
        """
        Build an AllocationEngine from an AuditInputBundle.

        If allocation_config is not passed directly, the engine tries to build it
        from bundle.specialization_requirements.allocation_config. If that is
        missing, the default AllocationConfig is used.
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
            options=bundle.options,
            allocation_config=allocation_config,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def allocate(
        self,
        classified_courses: pd.DataFrame,
        specialization_audit: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Allocate student courses to exclusive specialization buckets.

        Returns
        -------
        pd.DataFrame
            One row per student course.
        """

        allocation = classified_courses.copy().reset_index(drop=True)

        allocation = self._ensure_allocation_columns(allocation)

        counted_mask = self._counted_course_mask(allocation)

        allocation.loc[~counted_mask, "allocation_method"] = "not_counted_status"
        allocation.loc[~counted_mask, "allocation_notes"] = (
            "Course status not included in current audit options."
        )

        allocation = self._add_allocation_sort_columns(allocation)

        allocation = self._apply_allocation_overrides(
            allocation=allocation,
            specialization_audit=specialization_audit,
        )

        for bucket in self.config.priority_order:
            if bucket == "core":
                allocation = self._allocate_core_requirements(
                    allocation=allocation,
                    specialization_audit=specialization_audit,
                    bucket=bucket,
                )

            elif bucket == "tools":
                allocation = self._allocate_canonical_course_bucket(
                    allocation=allocation,
                    specialization_audit=specialization_audit,
                    bucket=bucket,
                    priority=20,
                    method="priority_tools",
                )

            elif bucket == "option":
                allocation = self._allocate_option_requirement(
                    allocation=allocation,
                    specialization_audit=specialization_audit,
                    bucket=bucket,
                    priority_specific=30,
                    priority_total=35,
                )

            elif bucket == "complementary":
                allocation = self._allocate_canonical_credit_bucket(
                    allocation=allocation,
                    specialization_audit=specialization_audit,
                    bucket=bucket,
                    priority=40,
                    method="priority_complementary",
                )

            elif bucket == self.config.residual_bucket:
                allocation = self._allocate_residual_electives(
                    allocation=allocation,
                    bucket=bucket,
                    priority=50,
                )

        allocation["also_counts_toward"] = allocation.apply(
            self._also_counts_toward,
            axis=1,
        )

        allocation = allocation.drop(
            columns=[
                "_status_priority",
                "_original_order",
            ],
            errors="ignore",
        )

        return allocation

    def build_allocated_specialization_audit(
        self,
        course_allocation: pd.DataFrame,
        specialization_audit: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Build post-allocation specialization audit.

        This answers:
        After exclusive assignment, which specialization requirements are satisfied?
        """

        rows = []

        for _, audit_row in specialization_audit.iterrows():
            rule_type = str(audit_row.get("rule_type", "")).strip()
            requirement_area = str(audit_row.get("requirement_area", "")).strip()

            bucket = self.resolver.bucket_for_row(audit_row)

            if bucket == "option" and rule_type in self.resolver.rule_types_for_bucket("option"):
                rows.append(
                    self._allocated_credit_bucket_row(
                        audit_row=audit_row,
                        course_allocation=course_allocation,
                        bucket=bucket,
                    )
                )

            elif bucket == "tools" and rule_type in self.resolver.rule_types_for_bucket("tools"):
                rows.append(
                    self._allocated_course_bucket_row(
                        audit_row=audit_row,
                        course_allocation=course_allocation,
                        bucket=bucket,
                    )
                )

            elif bucket == "complementary" and rule_type in self.resolver.rule_types_for_bucket("complementary"):
                rows.append(
                    self._allocated_credit_bucket_row(
                        audit_row=audit_row,
                        course_allocation=course_allocation,
                        bucket=bucket,
                    )
                )

            elif rule_type == "theme_minimum":
                rows.append(
                    self._allocated_theme_minimum_row(
                        audit_row=audit_row,
                        course_allocation=course_allocation,
                    )
                )

            elif bucket in {"core", "option"}:
                rows.append(
                    self._allocated_specific_group_row(
                        audit_row=audit_row,
                        course_allocation=course_allocation,
                        bucket=bucket,
                    )
                )

            else:
                preserved = audit_row.to_dict()
                preserved["allocated_status"] = preserved.get("status", "")
                preserved["allocated_completed"] = preserved.get("completed", "")
                preserved["allocated_required"] = preserved.get("required", "")
                preserved["allocated_remaining"] = preserved.get("remaining", "")
                preserved["allocated_surplus"] = preserved.get("surplus", "")
                preserved["allocated_unit"] = preserved.get("unit", "")
                preserved["allocated_courses"] = preserved.get("matched_courses", "")
                preserved["allocation_notes"] = (
                    "No allocation-specific recalculation for this row."
                )
                rows.append(preserved)

        return pd.DataFrame(rows)

    def write_outputs(
        self,
        course_allocation: pd.DataFrame,
        allocated_specialization_audit: pd.DataFrame,
        output_dir: str | Path,
    ) -> dict:
        """
        Write allocation outputs to CSV.
        """

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = {}

        course_allocation_path = output_dir / "course_allocation.csv"
        course_allocation.to_csv(course_allocation_path, index=False)
        paths["course_allocation"] = course_allocation_path

        allocated_audit_path = output_dir / "allocated_specialization_audit.csv"
        allocated_specialization_audit.to_csv(allocated_audit_path, index=False)
        paths["allocated_specialization_audit"] = allocated_audit_path

        return paths

    # ------------------------------------------------------------------
    # Allocation steps
    # ------------------------------------------------------------------

    def _apply_allocation_overrides(
        self,
        allocation: pd.DataFrame,
        specialization_audit: pd.DataFrame,
    ) -> pd.DataFrame:
        df = allocation.copy()

        for idx, row in df.iterrows():
            if not self._is_counted_row(row):
                continue

            if self._is_allocated(row):
                continue

            override_group_id = str(
                row.get("override_exclusive_group_id", "")
            ).strip()

            override_area = str(
                row.get("override_exclusive_requirement_area", "")
            ).strip()

            if override_group_id:
                group_info = self._lookup_audit_group(
                    specialization_audit,
                    override_group_id,
                )

                bucket = self.resolver.bucket_for_row_dict(group_info)

                display_area = group_info.get(
                    "requirement_area",
                    self.resolver.display_name_for_bucket(bucket),
                )

                df = self._assign_course(
                    df=df,
                    idx=idx,
                    requirement_area=display_area,
                    group_id=override_group_id,
                    label=group_info.get("label", ""),
                    rule_type=group_info.get("rule_type", ""),
                    bucket=bucket,
                    priority=1,
                    method="override_exclusive_group_id",
                    notes=row.get("override_note", ""),
                )

            elif override_area:
                bucket, display_area = self.resolver.normalize_override_area_to_bucket(
                    override_area
                )

                df = self._assign_course(
                    df=df,
                    idx=idx,
                    requirement_area=display_area,
                    group_id="",
                    label=f"Override to {display_area}",
                    rule_type="override_area",
                    bucket=bucket,
                    priority=2,
                    method="override_exclusive_requirement_area",
                    notes=row.get("override_note", ""),
                )

        return df

    def _allocate_core_requirements(
        self,
        allocation: pd.DataFrame,
        specialization_audit: pd.DataFrame,
        bucket: str,
    ) -> pd.DataFrame:
        df = allocation.copy()

        core_rows = self.resolver.df_for_bucket(
            specialization_audit,
            bucket,
        )

        core_rows = core_rows[
            ~core_rows["rule_type"].astype(str).str.strip().isin(
                self.resolver.rule_types_for_bucket(bucket)
            )
        ].copy()

        for _, group in core_rows.iterrows():
            df = self._allocate_group_requirement(
                allocation=df,
                audit_row=group,
                bucket=bucket,
                priority=10,
                method_prefix="priority_core",
            )

        return df

    def _allocate_canonical_course_bucket(
        self,
        allocation: pd.DataFrame,
        specialization_audit: pd.DataFrame,
        bucket: str,
        priority: int,
        method: str,
    ) -> pd.DataFrame:
        df = allocation.copy()

        rows = self.resolver.canonical_rows_for_bucket(
            specialization_audit,
            bucket,
        )

        if rows.empty:
            return df

        audit_row = rows.iloc[0]

        required_count = int(float(audit_row.get("required", 0)))

        if required_count <= 0:
            return df

        eligible_courses = self.resolver.get_eligible_courses_by_bucket(bucket)

        selected_indices = self._select_unallocated_eligible_indices(
            allocation=df,
            eligible_course_codes=eligible_courses,
            max_count=required_count,
        )

        for idx in selected_indices:
            df = self._assign_course(
                df=df,
                idx=idx,
                requirement_area=self.resolver.display_name_for_bucket(bucket),
                group_id=str(audit_row.get("group_id", "")),
                label=str(audit_row.get("label", self.resolver.display_name_for_bucket(bucket))),
                rule_type=str(audit_row.get("rule_type", "")),
                bucket=bucket,
                priority=priority,
                method=method,
                notes="",
            )

        return df

    def _allocate_canonical_credit_bucket(
        self,
        allocation: pd.DataFrame,
        specialization_audit: pd.DataFrame,
        bucket: str,
        priority: int,
        method: str,
    ) -> pd.DataFrame:
        df = allocation.copy()

        rows = self.resolver.canonical_rows_for_bucket(
            specialization_audit,
            bucket,
        )

        if rows.empty:
            return df

        audit_row = rows.iloc[0]

        required_credits = float(audit_row.get("required", 0))

        already_allocated_credits = df[
            df["exclusive_bucket"] == bucket
        ]["credits"].sum()

        remaining_credits = max(required_credits - already_allocated_credits, 0)

        if remaining_credits <= 0:
            return df

        eligible_courses = self.resolver.get_eligible_courses_by_bucket(bucket)

        selected_indices = self._select_unallocated_eligible_indices_by_credits(
            allocation=df,
            eligible_course_codes=eligible_courses,
            target_credits=remaining_credits,
        )

        for idx in selected_indices:
            df = self._assign_course(
                df=df,
                idx=idx,
                requirement_area=self.resolver.display_name_for_bucket(bucket),
                group_id=str(audit_row.get("group_id", "")),
                label=str(audit_row.get("label", self.resolver.display_name_for_bucket(bucket))),
                rule_type=str(audit_row.get("rule_type", "")),
                bucket=bucket,
                priority=priority,
                method=method,
                notes="",
            )

        return df

    def _allocate_option_requirement(
        self,
        allocation: pd.DataFrame,
        specialization_audit: pd.DataFrame,
        bucket: str,
        priority_specific: int,
        priority_total: int,
    ) -> pd.DataFrame:
        """
        Allocate selected option/AoC/stream/focus-area requirements.

        This method:
        1. Allocates specific option groups first.
        2. Then fills the option total-credit bucket with remaining eligible courses.
        """

        df = allocation.copy()

        option_id = str(self.profile.option_id or "").strip()

        if not option_id:
            return df

        option_rows = self.resolver.df_for_bucket(
            specialization_audit,
            bucket,
        )

        specific_rows = option_rows[
            ~option_rows["rule_type"].astype(str).str.strip().isin(
                self.resolver.rule_types_for_bucket(bucket) + ["theme_minimum"]
            )
        ].copy()

        for _, group in specific_rows.iterrows():
            df = self._allocate_group_requirement(
                allocation=df,
                audit_row=group,
                bucket=bucket,
                priority=priority_specific,
                method_prefix="priority_option_specific",
            )

        canonical_rows = self.resolver.canonical_rows_for_bucket(
            specialization_audit,
            bucket,
        )

        if canonical_rows.empty:
            return df

        total_row = canonical_rows.iloc[0]

        required_credits = float(total_row.get("required", 0))

        already_allocated_credits = df[
            df["exclusive_bucket"] == bucket
        ]["credits"].sum()

        remaining_credits = max(required_credits - already_allocated_credits, 0)

        if remaining_credits <= 0:
            return df

        eligible_courses = self.resolver.get_option_eligible_course_codes(
            option_id
        )

        selected_indices = self._select_unallocated_eligible_indices_by_credits(
            allocation=df,
            eligible_course_codes=eligible_courses,
            target_credits=remaining_credits,
        )

        for idx in selected_indices:
            df = self._assign_course(
                df=df,
                idx=idx,
                requirement_area=self.resolver.display_name_for_bucket(bucket),
                group_id=str(total_row.get("group_id", "")),
                label=str(total_row.get("label", self.resolver.display_name_for_bucket(bucket))),
                rule_type=str(total_row.get("rule_type", "")),
                bucket=bucket,
                priority=priority_total,
                method="priority_option_total",
                notes="",
            )

        return df

    def _allocate_residual_electives(
        self,
        allocation: pd.DataFrame,
        bucket: str,
        priority: int,
    ) -> pd.DataFrame:
        df = allocation.copy()

        for idx, row in df.iterrows():
            if not self._is_counted_row(row):
                continue

            if self._is_allocated(row):
                continue

            df = self._assign_course(
                df=df,
                idx=idx,
                requirement_area=self.resolver.display_name_for_bucket(bucket),
                group_id="",
                label=self.config.residual_label,
                rule_type="residual_elective",
                bucket=bucket,
                priority=priority,
                method="residual_elective",
                notes="Allocated as residual elective after priority requirements.",
            )

        return df

    # ------------------------------------------------------------------
    # Post-allocation specialization audit helpers
    # ------------------------------------------------------------------

    def _allocated_credit_bucket_row(
        self,
        audit_row: pd.Series,
        course_allocation: pd.DataFrame,
        bucket: str,
    ) -> dict:
        matched = course_allocation[
            self._allocation_counts_for_bucket(
                course_allocation,
                bucket,
            )
        ].copy()

        completed = matched["credits"].sum()
        required = float(audit_row.get("required", 0))

        return self._make_allocated_row(
            audit_row=audit_row,
            completed=completed,
            required=required,
            unit="credits",
            allocated_courses=self._course_list(matched),
            notes=f"Post-allocation credit bucket for {self.resolver.display_name_for_bucket(bucket)}.",
        )

    def _allocated_course_bucket_row(
        self,
        audit_row: pd.Series,
        course_allocation: pd.DataFrame,
        bucket: str,
    ) -> dict:
        matched = course_allocation[
            self._allocation_counts_for_bucket(
                course_allocation,
                bucket,
            )
        ].copy()

        completed = matched["effective_course_code"].drop_duplicates().shape[0]
        required = float(audit_row.get("required", 0))

        return self._make_allocated_row(
            audit_row=audit_row,
            completed=completed,
            required=required,
            unit="course",
            allocated_courses=self._course_list(matched),
            notes=f"Post-allocation course bucket for {self.resolver.display_name_for_bucket(bucket)}.",
        )

    def _allocated_specific_group_row(
        self,
        audit_row: pd.Series,
        course_allocation: pd.DataFrame,
        bucket: str,
    ) -> dict:
        group_id = str(audit_row.get("group_id", "")).strip()
        unit = str(audit_row.get("unit", "")).strip()
        required = float(audit_row.get("required", 0))

        matched = course_allocation[
            self._allocation_counts_for_specific_group(
                course_allocation=course_allocation,
                group_id=group_id,
            )
        ].copy()

        eligible_courses = self.resolver.get_group_course_codes(group_id)

        if eligible_courses:
            matched = self.resolver.filter_courses_by_eligible_codes(
                matched,
                eligible_courses,
            )

        if unit == "credits":
            completed = matched["credits"].sum()
        else:
            completed = min(
                matched["effective_course_code"].drop_duplicates().shape[0],
                required,
            )

        return self._make_allocated_row(
            audit_row=audit_row,
            completed=completed,
            required=required,
            unit=unit,
            allocated_courses=self._course_list(matched),
            notes="Post-allocation recalculation for specific requirement group.",
        )

    def _allocated_theme_minimum_row(
        self,
        audit_row: pd.Series,
        course_allocation: pd.DataFrame,
    ) -> dict:
        """
        First-pass theme-minimum handling.

        This preserves the original possible-match audit result. A more precise
        allocated theme-minimum recalculation can be added once we decide how
        strict theme-specific allocation should be.
        """

        preserved = audit_row.to_dict()
        preserved["allocated_status"] = preserved.get("status", "")
        preserved["allocated_completed"] = preserved.get("completed", "")
        preserved["allocated_required"] = preserved.get("required", "")
        preserved["allocated_remaining"] = preserved.get("remaining", "")
        preserved["allocated_surplus"] = preserved.get("surplus", "")
        preserved["allocated_unit"] = preserved.get("unit", "")
        preserved["allocated_courses"] = preserved.get("matched_courses", "")
        preserved["allocation_notes"] = (
            "Theme minimum allocation recalculation deferred; original audit preserved."
        )
        return preserved

    def _make_allocated_row(
        self,
        audit_row: pd.Series,
        completed,
        required,
        unit: str,
        allocated_courses: str,
        notes: str,
    ) -> dict:
        completed_value = float(completed) if completed is not None else 0
        required_value = float(required) if required is not None else 0

        remaining = max(required_value - completed_value, 0)
        surplus = max(completed_value - required_value, 0)

        if required_value == 0:
            status = "review"
        elif completed_value >= required_value:
            status = "satisfied"
        elif completed_value > 0:
            status = "partial"
        else:
            status = "missing"

        row = audit_row.to_dict()
        row["allocated_status"] = status
        row["allocated_completed"] = completed_value
        row["allocated_required"] = required_value
        row["allocated_remaining"] = remaining
        row["allocated_surplus"] = surplus
        row["allocated_unit"] = unit
        row["allocated_courses"] = allocated_courses
        row["allocation_notes"] = notes

        return row

    # ------------------------------------------------------------------
    # Requirement group allocation helpers
    # ------------------------------------------------------------------

    def _allocate_group_requirement(
        self,
        allocation: pd.DataFrame,
        audit_row: pd.Series,
        bucket: str,
        priority: int,
        method_prefix: str,
    ) -> pd.DataFrame:
        df = allocation.copy()

        group_id = str(audit_row.get("group_id", "")).strip()
        group_metadata = self.resolver.get_group_metadata(group_id)
        rule_type = str(
            group_metadata.get("rule_type", audit_row.get("rule_type", ""))
        ).strip()
        required = float(audit_row.get("required", 0))
        unit = str(audit_row.get("unit", "")).strip()

        if required <= 0:
            return df

        if rule_type == "level_requirement":
            eligible_indices = self._eligible_level_requirement_indices(
                allocation=df,
                audit_row=audit_row,
            )
        else:
            eligible_courses = self.resolver.get_group_course_codes(group_id)
            eligible_indices = self._eligible_unallocated_indices(
                allocation=df,
                eligible_course_codes=eligible_courses,
            )

        eligible_df = df.loc[eligible_indices].copy()

        if eligible_df.empty:
            return df

        if unit == "credits":
            selected_indices = self._select_indices_by_credits(
                eligible_df,
                target_credits=required,
            )
        else:
            selected_indices = self._select_indices_by_count(
                eligible_df,
                max_count=int(required),
            )

        for idx in selected_indices:
            df = self._assign_course(
                df=df,
                idx=idx,
                requirement_area=self.resolver.display_name_for_bucket(bucket),
                group_id=group_id,
                label=str(audit_row.get("label", "")),
                rule_type=rule_type,
                bucket=bucket,
                priority=priority,
                method=f"{method_prefix}_{rule_type}",
                notes="",
            )

        return df

    # ------------------------------------------------------------------
    # Candidate selection helpers
    # ------------------------------------------------------------------

    def _eligible_unallocated_indices(
        self,
        allocation: pd.DataFrame,
        eligible_course_codes: list[str],
    ) -> list:
        if not eligible_course_codes:
            return []

        eligible_set = {
            str(code).strip().upper()
            for code in eligible_course_codes
            if str(code).strip()
        }

        indices = []

        for idx, row in allocation.iterrows():
            if not self._is_counted_row(row):
                continue

            if self._is_allocated(row):
                continue

            student_code = str(row.get("effective_course_code", "")).strip().upper()

            if self.resolver.course_matches_any_eligible(student_code, eligible_set):
                indices.append(idx)

        return indices

    def _eligible_level_requirement_indices(
        self,
        allocation: pd.DataFrame,
        audit_row: pd.Series,
    ) -> list:
        group_id = str(audit_row.get("group_id", "")).strip()
    
        if not group_id:
            return []
    
        group_row = self.resolver.get_group_series(group_id)
    
        indices = []
    
        for idx, course_row in allocation.iterrows():
            if not self._is_counted_row(course_row):
                continue
    
            if self._is_allocated(course_row):
                continue
    
            if self.resolver.course_matches_level_requirement(
                course_row=course_row,
                group_row=group_row,
            ):
                indices.append(idx)
    
        return indices

    def _select_unallocated_eligible_indices(
        self,
        allocation: pd.DataFrame,
        eligible_course_codes: list[str],
        max_count: int,
    ) -> list:
        indices = self._eligible_unallocated_indices(
            allocation,
            eligible_course_codes,
        )

        eligible_df = allocation.loc[indices].copy()

        return self._select_indices_by_count(
            eligible_df,
            max_count=max_count,
        )

    def _select_unallocated_eligible_indices_by_credits(
        self,
        allocation: pd.DataFrame,
        eligible_course_codes: list[str],
        target_credits: float,
    ) -> list:
        indices = self._eligible_unallocated_indices(
            allocation,
            eligible_course_codes,
        )

        eligible_df = allocation.loc[indices].copy()

        return self._select_indices_by_credits(
            eligible_df,
            target_credits=target_credits,
        )

    def _select_indices_by_count(
        self,
        eligible_df: pd.DataFrame,
        max_count: int,
    ) -> list:
        if eligible_df.empty or max_count <= 0:
            return []

        sorted_df = eligible_df.sort_values(
            by=[
                "_status_priority",
                "term",
                "_original_order",
            ],
            ascending=[
                True,
                True,
                True,
            ],
        )

        return sorted_df.head(max_count).index.tolist()

    def _select_indices_by_credits(
        self,
        eligible_df: pd.DataFrame,
        target_credits: float,
    ) -> list:
        if eligible_df.empty or target_credits <= 0:
            return []

        sorted_df = eligible_df.sort_values(
            by=[
                "_status_priority",
                "term",
                "_original_order",
            ],
            ascending=[
                True,
                True,
                True,
            ],
        )

        selected = []
        total = 0.0

        for idx, row in sorted_df.iterrows():
            selected.append(idx)

            credits = row.get("credits", 0)

            if pd.isna(credits):
                credits = 0

            total += float(credits)

            if total >= target_credits:
                break

        return selected

    # ------------------------------------------------------------------
    # Requirement / course lookup helpers
    # ------------------------------------------------------------------

    def _lookup_audit_group(
        self,
        specialization_audit: pd.DataFrame,
        group_id: str,
    ) -> dict:
        rows = specialization_audit[
            specialization_audit["group_id"].astype(str) == group_id
        ]

        if rows.empty:
            return {}

        return rows.iloc[0].to_dict()

    # ------------------------------------------------------------------
    # Allocation column helpers
    # ------------------------------------------------------------------

    def _ensure_allocation_columns(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        df = df.copy()

        optional_input_columns = [
            "override_exclusive_group_id",
            "override_exclusive_requirement_area",
            "override_allow_double_count",
            "override_double_count_groups",
            "override_note",
        ]

        for column in optional_input_columns:
            if column not in df.columns:
                df[column] = ""

        allocation_columns = {
            "exclusive_requirement_area": "",
            "exclusive_group_id": "",
            "exclusive_label": "",
            "exclusive_rule_type": "",
            "exclusive_bucket": "",
            "allocation_priority": "",
            "allocation_method": "",
            "allocation_notes": "",
            "override_used": False,
            "double_count_allowed": False,
            "double_count_groups": "",
            "also_counts_toward": "",
        }

        for column, default in allocation_columns.items():
            if column not in df.columns:
                df[column] = default

        df["double_count_allowed"] = df["override_allow_double_count"].apply(
            self._to_bool
        )

        df["double_count_groups"] = df["override_double_count_groups"]

        return df

    def _assign_course(
        self,
        df: pd.DataFrame,
        idx,
        requirement_area: str,
        group_id: str,
        label: str,
        rule_type: str,
        bucket: str,
        priority: int,
        method: str,
        notes: str,
    ) -> pd.DataFrame:
        df = df.copy()

        df.at[idx, "exclusive_requirement_area"] = requirement_area
        df.at[idx, "exclusive_group_id"] = group_id
        df.at[idx, "exclusive_label"] = label
        df.at[idx, "exclusive_rule_type"] = rule_type
        df.at[idx, "exclusive_bucket"] = bucket
        df.at[idx, "allocation_priority"] = priority
        df.at[idx, "allocation_method"] = method
        df.at[idx, "allocation_notes"] = notes

        if method.startswith("override"):
            df.at[idx, "override_used"] = True

        return df

    @staticmethod
    def _is_allocated(row) -> bool:
        return bool(str(row.get("exclusive_requirement_area", "")).strip())

    def _is_counted_row(
        self,
        row,
    ) -> bool:
        status = str(row.get("status", "")).strip().lower()

        count_statuses = {
            status.strip().lower()
            for status in self.options.count_statuses
        }

        excluded_statuses = {
            "failed",
            "withdrawn",
            "w",
            "fail",
        }

        return status in count_statuses and status not in excluded_statuses

    def _counted_course_mask(
        self,
        df: pd.DataFrame,
    ) -> pd.Series:
        statuses = {
            status.strip().lower()
            for status in self.options.count_statuses
        }

        excluded = {
            "failed",
            "withdrawn",
            "w",
            "fail",
        }

        normalized = df["status"].astype(str).str.strip().str.lower()

        return normalized.isin(statuses) & ~normalized.isin(excluded)

    def _add_allocation_sort_columns(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        df = df.copy()

        priority = {
            "completed": 0,
            "in_progress": 1,
            "planned": 2,
        }

        df["_status_priority"] = (
            df["status"]
            .astype(str)
            .str.strip()
            .str.lower()
            .map(priority)
            .fillna(9)
        )

        df["_original_order"] = range(len(df))

        if "term" not in df.columns:
            df["term"] = ""

        return df

    # ------------------------------------------------------------------
    # Non-exclusive contribution helpers
    # ------------------------------------------------------------------

    def _also_counts_toward(
        self,
        row,
    ) -> str:
        values = ["Total Credits"]

        if bool(row.get("is_science_credit", False)):
            values.append("Science Credit")

        if bool(row.get("is_arts_credit", False)):
            values.append("Arts Credit")

        if bool(row.get("is_upper_level", False)):
            values.append("Upper-Level Credit")

        breadth = str(row.get("breadth_categories", "")).strip()

        if breadth:
            values.append(f"Science Breadth: {breadth}")

        faculty_matches = str(
            row.get("faculty_requirement_matches", "")
        ).strip()

        if faculty_matches:
            for item in faculty_matches.split(";"):
                item = item.strip()

                if item:
                    values.append(f"Faculty Requirement: {item}")

        return ";".join(values)

    def _allocation_counts_for_bucket(
        self,
        course_allocation: pd.DataFrame,
        bucket: str,
    ) -> pd.Series:
        bucket_match = (
            course_allocation["exclusive_bucket"]
            .astype(str)
            .str.strip()
            == bucket
        )

        double_match = course_allocation.apply(
            lambda row: self._double_count_matches_bucket(row, bucket),
            axis=1,
        )

        return bucket_match | double_match

    def _allocation_counts_for_specific_group(
        self,
        course_allocation: pd.DataFrame,
        group_id: str,
    ) -> pd.Series:
        group_match = (
            course_allocation["exclusive_group_id"]
            .astype(str)
            .str.strip()
            == group_id
        )

        double_match = course_allocation.apply(
            lambda row: self._double_count_matches_group(row, group_id),
            axis=1,
        )

        return group_match | double_match

    @staticmethod
    def _double_count_matches_group(
        row,
        group_id: str,
    ) -> bool:
        if not bool(row.get("double_count_allowed", False)):
            return False

        groups = str(row.get("double_count_groups", "")).split(";")

        return group_id in [
            group.strip()
            for group in groups
            if group.strip()
        ]

    @staticmethod
    def _double_count_matches_bucket(
        row,
        bucket: str,
    ) -> bool:
        if not bool(row.get("double_count_allowed", False)):
            return False

        groups = str(row.get("double_count_groups", "")).split(";")

        return bucket in [
            group.strip()
            for group in groups
            if group.strip()
        ]

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_bool(
        value,
    ) -> bool:
        value = str(value).strip().lower()

        return value in {
            "true",
            "yes",
            "y",
            "1",
        }

    @staticmethod
    def _course_list(
        courses: pd.DataFrame,
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