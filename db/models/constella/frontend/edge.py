from dataclasses import dataclass, field
from typing import Optional

@dataclass
class EdgeStyle:
    strokeWidth: int = 2
    stroke: str = "white"

@dataclass
class Edge:
    id: Optional[str] = None
    source: Optional[str] = None
    target: Optional[str] = None
    style: Optional[EdgeStyle] = field(default_factory=EdgeStyle)
    type: Optional[str] = "floating"
