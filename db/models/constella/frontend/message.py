from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class Message:
    sender: str  # "user" or "assistant"
    content: str
    timestamp: datetime = datetime.now()
    message_id: Optional[str] = None
    role: Optional[str] = None  # computed property based on sender

    def get_role(self) -> str:
        """Convert sender to role format expected by AI model"""
        return "user" if self.sender == "user" else "assistant"

    def to_dict(self) -> dict:
        """Convert message to dictionary format expected by AI model"""
        return {
            "role": self.get_role(),
            "content": self.content or ""
        }