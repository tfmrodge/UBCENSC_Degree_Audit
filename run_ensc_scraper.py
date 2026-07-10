# -*- coding: utf-8 -*-
"""
Created on Thu Jul  2 12:37:56 2026

@author: Timot
"""
import pdb
from scrape_calendar import run_scraper
import pandas as pd

#pdb.set_trace()

calyr="2024-2025" #"2026-2027" #"2024-2025" #
if calyr == "2024-2025":
    url = "https://archive.calendar.ubc.ca/vancouver/2425/faculties-colleges-and-schools/faculty-science/bachelor-science/environmental-sciences/index.html"
    output_dir="course_requirements/ensc_2024_2025"
    complementary_studies_url = None
elif calyr == "2026-2027":
    url = "https://vancouver.calendar.ubc.ca/faculties-colleges-and-schools/faculty-science/bachelor-science/environmental-sciences"
    output_dir="course_requirements/ensc_2026_2027"
    complementary_studies_url = 'https://www.eoas.ubc.ca/undergrads/degrees/environmental-sciences'

package = run_scraper(
    url=url,
    calendar_year=calyr,
    program="ENSC",
    output_dir=output_dir,
    complementary_url = complementary_studies_url)

df_courses = pd.read_csv(output_dir+'/requirement_courses.csv')
df_groups = pd.read_csv(output_dir+'/requirement_groups.csv')

print(package)