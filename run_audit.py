# -*- coding: utf-8 -*-
"""
Created on Tue Jul 7 15:44:28 2026

@author: Tim Rodgers w M365 Copilot

Run/test the audit pipeline.
"""

#from pathlib import Path

from audit.loaders import load_ensc_audit_case
from audit.models import AuditOptions
from audit.audit_engine import AuditEngine

import pdb
pdb.set_trace()

# ---------------------------------------------------------------------
# Runtime setup
# ---------------------------------------------------------------------

#student_case_dir = "student_inputs/example_student_001"
#student_case_dir = "student_inputs/example_student_honours_land_air_water"
student_case_dir = "student_inputs/example_student_002"
count_statuses = []
audit_mode = 'in-progress' #'planned' #'planned'
write_outputs = False
print_outputs = True

if audit_mode == 'planned':
        count_statuses=[
            "completed",
            "in_progress",
            "planned",
        ]
elif audit_mode == 'in-progress':
    count_statuses=[
        "completed",
        "in_progress",
    ]
elif audit_mode == 'completed':
    count_statuses=[
        "completed",
    ]

options = AuditOptions(
    count_statuses=count_statuses,
    audit_mode=audit_mode,
)


bundle = load_ensc_audit_case(
    student_case_dir=student_case_dir,
    root_dir=".",
    options=options,
)

engine = AuditEngine.from_bundle(bundle)

working = engine.run()

faculty_audit_summary = working.faculty_audit_summary
promotion_audit = working.promotion_audit
specialization_audit = working.specialization_audit
course_allocation = working.course_allocation
allocated_specialization_audit = working.allocated_specialization_audit

if print_outputs:
    engine.print_summary(
        working,
        max_missing_rows=12,
        max_courses_to_show=3,
    )
if write_outputs:
    output_paths = engine.write_outputs(
        working,
        base_output_dir="audit_outputs",
    )
    print()
    print("Outputs written:")
    for name, path in output_paths.items():
        print(f"- {name}: {path}")