UBC ENSC Degree Audit - First Draft
===================================

Overview
--------
This repository contains a first-draft degree audit pipeline for the UBC Environmental Sciences program. The audit loads student course records, Faculty of Science rules, specialization requirements, promotion rules, and allocation configuration files, then produces draft audit outputs for advising and testing.

This project is an early prototype. It is not an official advising, promotion, or graduation-clearance tool. Results should be reviewed by a knowledgeable advisor before being used for decisions.

Core Workflow
-------------
The current pipeline is coordinated by AuditEngine and runs these stages:

1. Load audit inputs
2. Classify student courses
3. Run Faculty-level audit
4. Run specialization possible-match audit
5. Run promotion audit
6. Allocate courses to exclusive specialization buckets
7. Build post-allocation specialization audit
8. Write CSV outputs and print a concise console summary

Main Components
---------------
- CourseClassifier
  Adds course-level attributes such as effective course code, subject, course number, Science/Arts credit flags, upper-level status, breadth categories, lab flags, and communication flags.

- FacultyAuditor
  Checks Faculty-level aggregate requirements, including total credits, Science credits, Arts credits, upper-level credits, Science breadth, laboratory requirement, communication requirement, and the cap on non-Arts/non-Science credits.

- SpecializationRequirementResolver
  Centralizes access to specialization requirement metadata, eligible course lists, applicable groups, bucket mappings, and level-requirement matching logic.

- SpecializationAuditor
  Produces a possible-match specialization audit before exclusivity is enforced. This helps identify which requirements courses could satisfy.

- PromotionAuditor
  Checks promotion requirements using classified courses and promotion_rules.csv.

- AllocationEngine
  Assigns each counted course to one exclusive specialization bucket, while preserving non-exclusive Faculty contributions such as Science credit, breadth, lab, communication, and total credits.

- AuditEngine
  Coordinates the full pipeline, writes outputs, and prints a concise summary.

Input Structure
---------------
Typical input folders are:

student_inputs/
  example_student_001/
    student_profile.csv
    student_courses.csv

course_requirements/
  ensc_2026_2027/
    requirement_groups.csv
    requirement_courses.csv
    footnotes.csv
    allocation_config.csv

faculty_requirements/
  faculty_course_classification_rules.csv
  faculty_breadth_categories.csv
  faculty_requirement_rules.csv
  faculty_requirement_courses.csv
  promotion_rules.csv

Student Course Overrides
------------------------
student_courses.csv supports overrides used during classification and allocation:

- override_course_code
  Treats a course as another course for matching.

- override_exclusive_group_id
  Forces a course into a specific specialization requirement group.

- override_exclusive_requirement_area
  Forces a course into a broader allocation area or bucket, such as Complementary Studies or option.

- override_allow_double_count
  Allows a course to count toward more than one normally exclusive bucket.

- override_double_count_groups
  Semicolon-separated list of approved double-count group IDs or bucket names.

- override_note
  Documents the reason for the override.

Allocation Buckets
------------------
Allocation is configured through allocation_config.csv. The default ENSC buckets are:

- core
- tools
- option
- complementary
- electives

These buckets map program-specific requirement labels, such as Area of Concentration or Complementary Studies, into generic allocation concepts. This allows future programs to use different naming conventions without rewriting the allocation engine.

Possible-Match vs Allocated Specialization Audit
------------------------------------------------
The pipeline produces two specialization-related outputs:

- specialization_audit.csv
  Shows possible requirement satisfaction before exclusivity is enforced.

- allocated_specialization_audit.csv
  Shows requirement satisfaction after exclusive course allocation. This is usually the more student-facing specialization result.

Faculty Rules and Credit Limits
-------------------------------
Faculty-level requirements are audited separately from specialization allocation. The non-Arts/non-Science credit cap is evaluated as a Faculty requirement. Total credits are not reduced by excess non-Arts/non-Science credits; instead, the cap is reported separately so the issue is visible.

Outputs
-------
Audit outputs are written to:

audit_outputs/<case_id>/

Current output files include:

- course_classification.csv
- faculty_audit_summary.csv
- specialization_audit.csv
- promotion_audit.csv
- course_allocation.csv
- allocated_specialization_audit.csv

Running the Audit
-----------------
A typical run script loads a case, creates an AuditEngine, runs the audit, prints a summary, and writes outputs:

from audit.loaders import load_ensc_audit_case
from audit.models import AuditOptions
from audit.audit_engine import AuditEngine

student_case_dir = "student_inputs/example_student_001"

options = AuditOptions(
    count_statuses=["completed", "in_progress", "planned"],
    audit_mode="planning",
)

bundle = load_ensc_audit_case(
    student_case_dir=student_case_dir,
    root_dir=".",
    options=options,
)

engine = AuditEngine.from_bundle(bundle)
working = engine.run()

engine.print_summary(working)
output_paths = engine.write_outputs(working)

Current Limitations
-------------------
- This is a first draft and not an official advising tool.
- Allocation is greedy and deterministic, not globally optimized.
- Theme-minimum allocation may need further refinement.
- Parser and scraper outputs still require review for edge cases.
- More test cases are needed, especially for Honours, transfer credits, substitutions, overrides, and double-counting.
- Faculty and specialization rules should be reviewed against the official calendar before use.

AI Disclosure
-------------
Portions of the code in this repository were generated or revised with assistance from Microsoft 365 Copilot. This README was also generated with assistance from Microsoft 365 Copilot, following common README best practices for project overview, setup context, architecture summary, limitations, and usage notes.

Recommended Next Steps
----------------------
1. Add automated tests for loaders, course classification, Faculty audit, specialization audit, promotion audit, and allocation.
2. Add more representative student test cases.
3. Improve allocation edge-case handling and consider an optimizer for complex conflicts.
4. Refine allocated theme-minimum logic.
5. Add an overall audit summary CSV.
6. Continue improving scraper filtering for advising or policy text that should not create course requirements.
7. Review Faculty and specialization rule files against official calendar requirements.
