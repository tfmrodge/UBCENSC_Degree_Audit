# -*- coding: utf-8 -*-
"""
Created on Thu Jul  2 12:37:56 2026

@author: Timot
"""
import pdb
from scrape_calendar import run_scraper


url = "https://vancouver.calendar.ubc.ca/faculties-colleges-and-schools/faculty-science/bachelor-science/environmental-sciences"

package = run_scraper(
    url=url,
    calendar_year="2026-2027",
    program="ENSC",
    output_dir="output/ensc_2026_2027"
)

print(package)