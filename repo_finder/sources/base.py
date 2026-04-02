from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional

import httpx


@dataclass
class FoundResult:
    source_name: str
    url: str
    description: str
    clone_url: Optional[str] = None
    confidence: str = "medium"  # "high", "medium", "low"
    timestamp: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class BaseSource(ABC):
    name: str = "Unknown"

    @abstractmethod
    async def search(
        self, owner: str, repo: str, session: httpx.AsyncClient
    ) -> list[FoundResult]:
        """Search this source for archived copies. Returns list of results."""
        ...
