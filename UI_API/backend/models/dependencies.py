from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RouteDependencies:
    ollama_semaphore: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "ollama_semaphore": self.ollama_semaphore,
        }
