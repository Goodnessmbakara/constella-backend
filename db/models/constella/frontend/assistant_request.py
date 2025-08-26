from dataclasses import dataclass
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
from db.models.constella.frontend.node import Node, Tag
from db.models.constella.frontend.edge import Edge
from db.models.constella.frontend.viewport import Viewport


class AssistantRequest(BaseModel):
	tenant_name: str
	user_message: str
	nodes: List[Node]
	edges: List[Edge]
	viewport: Viewport
	convo_mode_enabled: bool = True
	messages: List[dict] = Field(default_factory=list)
	tags: List[dict] = Field(default_factory=list)
