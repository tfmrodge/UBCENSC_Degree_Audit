# -*- coding: utf-8 -*-
"""
Created on Thu Jul  2 12:31:57 2026

@author: Tim Rodgers with MS Copilot
"""

import requests


class CalendarScraper:

    def download(self, url: str) -> str:
        response = requests.get(
            url,
            headers={
                "User-Agent": "ENSC Audit Tool Prototype"
            },
            timeout=30
        )
        response.raise_for_status()
        return response.text