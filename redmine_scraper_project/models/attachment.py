"""
Attachment data model.
"""

from dataclasses import dataclass, asdict


@dataclass
class Attachment:

    attachment_id: int = None
    filename: str = ""
    url: str = ""
    size: str = ""

    def to_dict(self):
        return asdict(self)
