"""
Journal data model.
"""

from dataclasses import dataclass, field, asdict
from typing import List


@dataclass
class Journal:

    journal_id: str = ""
    author: str = ""
    timestamp: str = ""
    content: str = ""
    changes: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
