"""
Relation data model.
"""

from dataclasses import dataclass, asdict


@dataclass
class Relation:

    type: str = ""
    target_issue: int = None

    def to_dict(self):
        return asdict(self)
