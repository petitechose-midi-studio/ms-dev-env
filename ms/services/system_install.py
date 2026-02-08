# SPDX-License-Identifier: MIT
"""Install a small, safe subset of host dependencies.

This is intentionally conservative:
- It never executes arbitrary shell snippets from hints.
- It only auto-executes a small allowlist of well-known installers.

Hints that don't match the safe allowlist are returned as manual steps.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from dataclasses import dataclass

from ms.output.console import ConsoleProtocol, Style
from ms.services.checkers.base import CheckResult
from ms.services.checkers.common import CommandRunner, DefaultCommandRunner

__all__ = ["InstallPlan", "InstallStep", "SystemInstaller"]


@dataclass(frozen=True, slots=True)
class InstallStep:
    name: str
    argv: list[str]

    @property
    def display(self) -> str:
        return shlex.join(self.argv)


@dataclass(frozen=True, slots=True)
class InstallPlan:
    steps: list[InstallStep]
    manual: list[tuple[str, str]]

    @property
    def is_empty(self) -> bool:
        return not self.steps and not self.manual


_MANUAL_PREFIXES = (
    "Run:",
    "N/A",
    "Install ",
    "Enable ",
    "Download ",
    "http://",
    "https://",
)

_SHELL_META = {
    "|",
    "||",
    "&&",
    ";",
    ">",
    ">>",
    "<",
    "2>",
    "&>",
}

_SAFE_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("sudo", "apt", "install"),
    ("sudo", "dnf", "install"),
    ("sudo", "pacman", "-S"),
    ("brew", "install"),
    ("winget", "install"),
)

_SAFE_EXACT: tuple[tuple[str, ...], ...] = (("xcode-select", "--install"),)


@dataclass(slots=True)
class _GroupedInstall:
    key: tuple[str, ...]
    prefix: tuple[str, ...]
    manager: str
    options: list[str]
    packages: list[str]
    names: list[str]


def _split_install_argv(argv: list[str]) -> _GroupedInstall | None:
    """Return a grouping descriptor for a safe install argv.

    Only a subset of installers support multi-package installs.
    """
    if tuple(argv) in _SAFE_EXACT:
        return None

    def split(
        prefix: tuple[str, ...], *, manager: str, key: tuple[str, ...] | None = None
    ) -> _GroupedInstall:
        rest = argv[len(prefix) :]
        options: list[str] = []
        packages: list[str] = []
        for tok in rest:
            if tok.startswith("-"):
                if tok not in options:
                    options.append(tok)
            else:
                if tok not in packages:
                    packages.append(tok)
        return _GroupedInstall(
            key=key or prefix,
            prefix=prefix,
            manager=manager,
            options=options,
            packages=packages,
            names=[],
        )

    if tuple(argv[:3]) == ("sudo", "apt", "install"):
        return split(("sudo", "apt", "install"), manager="apt")
    if tuple(argv[:3]) == ("sudo", "dnf", "install"):
        return split(("sudo", "dnf", "install"), manager="dnf")
    if tuple(argv[:3]) == ("sudo", "pacman", "-S"):
        return split(("sudo", "pacman", "-S"), manager="pacman")
    if tuple(argv[:2]) == ("brew", "install"):
        # Keep brew variants separate (e.g. --cask).
        rest = argv[2:]
        opts = tuple(tok for tok in rest if tok.startswith("-"))
        key = ("brew", "install", *opts)
        return split(("brew", "install"), manager="brew", key=key)

    # winget doesn't support multi-package install; keep as-is.
    return None


def _group_steps(steps: list[InstallStep]) -> list[InstallStep]:
    grouped: dict[tuple[str, ...], _GroupedInstall] = {}
    out: list[InstallStep | tuple[str, ...]] = []
    seen_verbatim: set[tuple[str, ...]] = set()

    for step in steps:
        spec = _split_install_argv(step.argv)
        if spec is None:
            key = tuple(step.argv)
            if key in seen_verbatim:
                continue
            seen_verbatim.add(key)
            out.append(step)
            continue

        g = grouped.get(spec.key)
        if g is None:
            g = spec
            grouped[spec.key] = g
            out.append(spec.key)

        if step.name not in g.names:
            g.names.append(step.name)

        for opt in spec.options:
            if opt not in g.options:
                g.options.append(opt)

        for pkg in spec.packages:
            if pkg not in g.packages:
                g.packages.append(pkg)

    result: list[InstallStep] = []
    for item in out:
        if isinstance(item, InstallStep):
            result.append(item)
            continue

        g = grouped[item]
        name = f"{g.manager}: {', '.join(g.names)}" if g.names else g.manager
        argv = [*g.prefix, *g.options, *g.packages]
        result.append(InstallStep(name=name, argv=argv))

    return result


def _is_manual_hint(hint: str) -> bool:
    stripped = hint.strip()
    return stripped.startswith(_MANUAL_PREFIXES)


def _parse_safe_install_argv(hint: str) -> list[str] | None:
    """Parse a safe, non-shell install command from a hint string."""
    if _is_manual_hint(hint):
        return None

    try:
        argv = shlex.split(hint, posix=True)
    except ValueError:
        return None

    if not argv:
        return None

    if any(tok in _SHELL_META for tok in argv):
        return None

    for prefix in _SAFE_PREFIXES:
        if tuple(argv[: len(prefix)]) == prefix and len(argv) > len(prefix):
            return argv

    for exact in _SAFE_EXACT:
        if tuple(argv) == exact:
            return argv

    return None


class SystemInstaller:
    """Build and execute a safe installation plan from check results."""

    def __init__(
        self,
        *,
        console: ConsoleProtocol,
        runner: CommandRunner | None = None,
        confirm: Callable[[str], bool] | None = None,
    ) -> None:
        self._console = console
        self._runner = runner or DefaultCommandRunner()
        self._confirm = confirm

    def plan_installation(self, results: list[CheckResult]) -> InstallPlan:
        steps: list[InstallStep] = []
        manual: list[tuple[str, str]] = []

        for r in results:
            hint = (r.hint or "").strip()
            if not hint:
                continue
            argv = _parse_safe_install_argv(hint)
            if argv is None:
                manual.append((r.name, hint))
            else:
                steps.append(InstallStep(name=r.name, argv=argv))

        return InstallPlan(steps=_group_steps(steps), manual=manual)

    def apply(self, plan: InstallPlan, *, dry_run: bool, assume_yes: bool) -> bool:
        if plan.is_empty:
            return True

        success = True

        if plan.steps:
            self._console.header("Install")
            for step in plan.steps:
                self._console.print(f"  {step.display}", Style.DIM)
            self._console.newline()

            if dry_run:
                self._console.print("Dry-run: not executing install commands", Style.DIM)
            elif assume_yes:
                for step in plan.steps:
                    self._console.print(f"Running: {step.display}", Style.DIM)
                    result = self._runner.run(step.argv, capture=False)
                    if result.returncode != 0:
                        self._console.error(f"Install failed: {step.name}")
                        success = False
                        break
                    self._console.success(f"Installed: {step.name}")
            elif self._confirm is None:
                self._console.error("Cannot prompt for confirmation (no prompt available)")
                success = False
            elif not self._confirm("Run the install commands above?"):
                self._console.warning("Skipped install commands")
                success = False
            else:
                for step in plan.steps:
                    self._console.print(f"Running: {step.display}", Style.DIM)
                    result = self._runner.run(step.argv, capture=False)
                    if result.returncode != 0:
                        self._console.error(f"Install failed: {step.name}")
                        success = False
                        break
                    self._console.success(f"Installed: {step.name}")

        if plan.manual:
            self._console.header("Manual steps")
            for name, hint in plan.manual:
                self._console.print(f"  {name}: {hint}", Style.WARNING)

        return success
