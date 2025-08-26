from dataclasses import dataclass, field
from typing import List, Optional, Any
from datetime import datetime

@dataclass
class Position:
	x: Optional[float] = None
	y: Optional[float] = None
	quadrant: Optional[int] = None
	radius: Optional[float] = None
	width: Optional[float] = None

@dataclass
class RxdbData:
	uniqueid: Optional[str] = None
	# vector: List[Any] | dict = field(default_factory=list) Ignore vector to save on context
	title: str = ""
	content: str = ""
	fileText: Optional[str] = "" # Has the file contents (for docs / images — embedding description)
	filePath: str = ""
	tags: List[Any] = field(default_factory=list)
	created: int = 0
	lastModified: int = 0
	incomingConnections: List[str] = field(default_factory=list)
	outgoingConnections: List[str] = field(default_factory=list)
	autoFocus: bool = False
	fileData: Optional[Any] = None
	helperFunctions: dict = field(default_factory=dict)

	# def __post_init__(self):
	# 	if isinstance(self.vector, dict):
	# 		self.vector = list(self.vector.values())

@dataclass
class Note:
	uniqueid: str
	# vector: List[Any] | dict = field(default_factory=list) Ignore vector to save on context
	position: Position = field(default_factory=Position)
	rxdbData: RxdbData = field(default_factory=RxdbData)

	# def __post_init__(self):
	# 	if isinstance(self.vector, dict):
	# 		self.vector = list(self.vector.values())

@dataclass
class Data:
	note: Note
	
@dataclass
class Node:
	id: str
	data: Data
	position: Position
	type: Optional[str] = None

# NOTE: there is also a Tag class in the assistant.py file, make sure to keep them in sync
# This one doesn't use BaseModel for easier parsing in without validation errors
@dataclass
class Tag:
	uniqueid: str
	name: str
	color: str