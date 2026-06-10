"""
Issue data model — canonical JSON schema.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict


@dataclass
class Issue:

    issue_id: int = None
    tracker: str = ""
    subject: str = ""

    project: str = ""
    status: str = ""
    priority: str = ""

    author: str = ""
    assignee: str = ""
    category: str = ""
    target_version: str = ""

    start_date: str = ""
    due_date: str = ""
    done_ratio: str = ""
    estimated_time: str = ""
    spent_time: str = ""

    created_on: str = ""
    updated_on: str = ""

    description: str = ""

    custom_fields: Dict[str, str] = field(default_factory=dict)

    attachments: List[dict] = field(default_factory=list)

    relations: List[dict] = field(default_factory=list)

    journals: List[dict] = field(default_factory=list)

    wiki_links: List[str] = field(default_factory=list)

    def to_dict(self):
        """Return the canonical JSON representation."""
        return asdict(self)
