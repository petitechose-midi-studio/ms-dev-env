from __future__ import annotations

from ms.cli.commands.status_models import RepoStatus


def generate_plain_text(changed: list[RepoStatus], clean: list[RepoStatus], detailed: bool) -> str:
    """Generate plain-text status output used for clipboard export."""
    lines: list[str] = []

    if changed:
        lines.append("PENDING")
        lines.append("")
        for repo in changed:
            if repo.error:
                lines.append(f"{repo.name}")
                lines.append(f"  error: {repo.error}")
            else:
                status = repo.status
                assert status is not None

                lines.append(f"{repo.name}")
                lines.append(f"{repo.path}")
                lines.append(f"{status.branch}  {repo.counts.as_string()}")

                if detailed and status.entries:
                    for entry in status.entries:
                        char = (
                            "?"
                            if entry.xy == "??"
                            else entry.xy[0]
                            if entry.xy[0] != " "
                            else entry.xy[1]
                        )
                        lines.append(f"  {char} {entry.path}")

            lines.append("")

    if clean:
        lines.append(f"OK ({len(clean)})")
        for repo in clean:
            lines.append(f"  {repo.name}")

    return "\n".join(lines)
