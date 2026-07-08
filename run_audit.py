# -*- coding: utf-8 -*-
"""
Created on Tue Jul  7 15:44:28 2026

@author: Tim Rodgers

Run the loader. 
"""

import pandas as pd

from audit.loaders import load_ensc_audit_case
from audit.models import AuditOptions
from audit.course_classifier import CourseClassifier

import pdb
pdb.set_trace()
student_case_dir = "student_inputs/example_student_001"

options = AuditOptions(
    count_statuses=[
        "completed",
        "in_progress",
        "planned",
    ],
    audit_mode="planning",
)

bundle = load_ensc_audit_case(
    student_case_dir=student_case_dir,
    root_dir=".",
    options=options,
)


classifier = CourseClassifier.from_audit_bundle(bundle)
classified_courses = classifier.classify()

print("Classified courses")
print("------------------")
print(
    classified_courses[
        [
            "course_code",
            "effective_course_code",
            "status",
            "credits",
            "subject",
            "course_number",
            "course_level",
            "is_science_credit",
            "is_arts_credit",
            "is_upper_level",
            "breadth_categories",
            "classification_notes",
        ]
    ]
)
