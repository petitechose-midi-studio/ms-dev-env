from __future__ import annotations

import re
from dataclasses import dataclass

from ms.services.release.model import ReleaseBump


_STABLE_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_BETA_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-beta\.(0|[1-9]\d*)$")


@dataclass(frozen=True, slots=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    def to_tag(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    def bump(self, kind: ReleaseBump) -> "SemVer":
        match kind:
            case "major":
                return SemVer(self.major + 1, 0, 0)
            case "minor":
                return SemVer(self.major, self.minor + 1, 0)
            case "patch":
                return SemVer(self.major, self.minor, self.patch + 1)
            case _:
                raise AssertionError(f"unexpected bump kind: {kind}")


def parse_stable_tag(tag: str) -> SemVer | None:
    m = _STABLE_RE.match(tag)
    if m is None:
        return None
    return SemVer(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def parse_beta_tag(tag: str) -> tuple[SemVer, int] | None:
    m = _BETA_RE.match(tag)
    if m is None:
        return None
    base = SemVer(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    n = int(m.group(4))
    return (base, n)


def format_beta_tag(base: SemVer, n: int) -> str:
    return f"{base.to_tag()}-beta.{n}"
