from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class AuthConfig:
    api_key: Optional[str] = field(default=None, repr=False)
    bearer: Optional[str] = field(default=None, repr=False)

    def apply(self, headers: Dict[str, str]) -> Dict[str, str]:
        resolved = dict(headers)
        if self.api_key:
            resolved["X-API-Key"] = self.api_key
        if self.bearer:
            resolved["Authorization"] = f"Bearer {self.bearer}"
        return resolved
