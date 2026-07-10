# -*- coding: utf-8 -*-
"""
Created on Thu Jul  2 12:29:48 2026

@author: Tim Rodgers with MS Copilot
"""

from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Requirement:
    id: str
    name: str
    courses: list[str] = field(default_factory=list)

@dataclass
class Concentration:
    name: str
    courses: list[str] = field(default_factory=list)

@dataclass
class RequirementPackage:
    program: str
    calendar_year: str

    requirements: list[Requirement] = field(default_factory=list)
    concentrations: list[Concentration] = field(default_factory=list)

@dataclass
class ProgramBlock:
    """
    Represents a specialization block, e.g.
    Major (1263): Environmental Sciences (ENSC)
    """
    program: str
    calendar_year: str
    program_type: str
    specialization_code: Optional[str]
    title: str
    heading_text: str


@dataclass
class RequirementGroup:
    """
    Represents one parsed requirement group.

    This can come from:
    - a program curriculum table
    - an Area of Concentration section
    - Complementary Studies
    - later, faculty or promotion rules
    """
    group_id: str
    program: str
    calendar_year: str
    program_type: str
    year_level: Optional[str]
    label: str
    credits: Optional[float]
    rule_type: str
    rule_value: Optional[int] = None
    source_text: str = ""
    courses: list[str] = field(default_factory=list)

    # Generalized requirement metadata
    requirement_area: Optional[str] = None

    # Generic option/pathway/track metadata
    option_id: Optional[str] = None
    option_name: Optional[str] = None
    option_name_raw: Optional[str] = None

    # Optional subcategory/theme within a requirement or option
    theme: Optional[str] = None
    
    #Rules for when you need a pattern    
    rule_subject: Optional[str] = None
    include_pattern: Optional[str] = None
    exclude_pattern: Optional[str] = None
    rule_unit: Optional[str] = None


    # General flags
    is_recommended: bool = False



@dataclass
class Footnote:
    """
    Represents a footnote from a curriculum table.
    Many actual rules are hidden in footnotes.
    """
    footnote_id: str
    program: str
    calendar_year: str
    program_type: str
    footnote_number: str
    text: str
    courses: list[str] = field(default_factory=list)


@dataclass
class RequirementPackage:
    """
    Main object returned by the parser.
    """
    program: str
    calendar_year: str

    program_blocks: list[ProgramBlock] = field(default_factory=list)
    requirement_groups: list[RequirementGroup] = field(default_factory=list)
    footnotes: list[Footnote] = field(default_factory=list)

    # Legacy fields from earlier prototype
    requirements: list[Requirement] = field(default_factory=list)
    concentrations: list[Concentration] = field(default_factory=list)
