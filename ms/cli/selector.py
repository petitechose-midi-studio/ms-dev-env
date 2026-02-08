from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from typing import Literal, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SelectorOption[T]:
    value: T
    label: str
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class SelectorResult[T]:
    action: Literal["select", "back", "cancel"]
    value: T | None
    index: int


_COMMIT_LABEL = re.compile(r"^([0-9a-f]{7,40})\s{2,}(.*)$")


def is_interactive_terminal() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def _color_enabled() -> bool:
    if not is_interactive_terminal():
        return False
    if os.getenv("NO_COLOR") is not None:
        return False
    term = os.getenv("TERM", "")
    return term.lower() != "dumb"


def _paint(text: str, *codes: str) -> str:
    if not _color_enabled() or not codes:
        return text
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def _clear() -> None:
    sys.stdout.write("\x1b[2J\x1b[H")


def _read_key() -> str:
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            return "enter"
        if ch in ("\x08", "\x7f"):
            return "back"
        if ch in ("q", "Q"):
            return "cancel"
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            if ch2 == "H":
                return "up"
            if ch2 == "P":
                return "down"
            return "other"
        return "other"

    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch in ("\r", "\n"):
            return "enter"
        if ch in ("\x08", "\x7f"):
            return "back"
        if ch in ("q", "Q"):
            return "cancel"
        if ch == "\x1b":
            c2 = sys.stdin.read(1)
            if c2 == "[":
                c3 = sys.stdin.read(1)
                if c3 == "A":
                    return "up"
                if c3 == "B":
                    return "down"
            return "cancel"
        return "other"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def _pad(text: str, width: int) -> str:
    return _truncate(text, width).ljust(width)


def _cols() -> int:
    return max(72, min(140, shutil.get_terminal_size((100, 30)).columns))


def _split_commit_label(label: str) -> tuple[str, str] | None:
    m = _COMMIT_LABEL.match(label.strip())
    if m is None:
        return None
    return m.group(1), m.group(2)


def _is_commit_mode(options: list[SelectorOption[object]]) -> bool:
    if not options:
        return False
    return all(_split_commit_label(opt.label) is not None for opt in options)


def _line(widths: list[int]) -> str:
    return "+" + "+".join("-" * (w + 2) for w in widths) + "+"


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _print_header(*, title: str, subtitle: str | None) -> None:
    print(_paint(title, "1", "96"))
    if subtitle is not None:
        print(_paint(subtitle, "2", "37"))
    print()


def _style_selected(text: str) -> str:
    return _paint(text, "1", "30", "46")


def _render_generic(*, options: list[SelectorOption[object]], index: int) -> None:
    cols = _cols()
    idx_w = 4
    option_w = max(20, min(44, int(cols * 0.38)))
    detail_w = max(18, cols - (idx_w + option_w + 10))
    widths = [idx_w, option_w, detail_w]

    print(_line(widths))
    print(
        _row(
            [
                _paint(_pad("Sel", idx_w), "1", "95"),
                _paint(_pad("Option", option_w), "1", "95"),
                _paint(_pad("Details", detail_w), "1", "95"),
            ]
        )
    )
    print(_line(widths))

    for i, opt in enumerate(options):
        marker = f">>{i + 1:02d}" if i == index else f"  {i + 1:02d}"
        c1 = _pad(marker, idx_w)
        c2 = _pad(opt.label.strip(), option_w)
        c3 = _pad((opt.detail or "").strip(), detail_w)

        if i == index:
            print(_row([_style_selected(c1), _style_selected(c2), _style_selected(c3)]))
        else:
            print(
                _row(
                    [
                        _paint(c1, "36"),
                        _paint(c2, "97"),
                        _paint(c3, "2", "37"),
                    ]
                )
            )

    print(_line(widths))


def _render_commits(*, options: list[SelectorOption[object]], index: int) -> None:
    parsed = [_split_commit_label(opt.label) for opt in options]
    rows: list[tuple[str, str, str]] = []
    for i, p in enumerate(parsed):
        if p is None:
            rows.append(("", options[i].label, options[i].detail or ""))
        else:
            rows.append((p[0], p[1], (options[i].detail or "").strip()))

    cols = _cols()
    idx_w = 4
    sha_w = max(10, min(14, max(len(r[0]) for r in rows)))
    date_w = max(12, min(24, max(len(r[2]) for r in rows)))
    msg_w = max(20, cols - (idx_w + sha_w + date_w + 12))
    widths = [idx_w, sha_w, msg_w, date_w]

    print(_line(widths))
    print(
        _row(
            [
                _paint(_pad("Sel", idx_w), "1", "95"),
                _paint(_pad("SHA", sha_w), "1", "95"),
                _paint(_pad("Message", msg_w), "1", "95"),
                _paint(_pad("Date", date_w), "1", "95"),
            ]
        )
    )
    print(_line(widths))

    for i, (sha, msg, date_s) in enumerate(rows):
        marker = f">>{i + 1:02d}" if i == index else f"  {i + 1:02d}"
        c1 = _pad(marker, idx_w)
        c2 = _pad(sha, sha_w)
        c3 = _pad(msg, msg_w)
        c4 = _pad(date_s, date_w)

        if i == index:
            print(
                _row(
                    [
                        _style_selected(c1),
                        _style_selected(c2),
                        _style_selected(c3),
                        _style_selected(c4),
                    ]
                )
            )
        else:
            print(
                _row(
                    [
                        _paint(c1, "36"),
                        _paint(c2, "1", "33"),
                        _paint(c3, "97"),
                        _paint(c4, "2", "37"),
                    ]
                )
            )

    print(_line(widths))


def _render(
    *, title: str, subtitle: str | None, options: list[SelectorOption[object]], index: int
) -> None:
    _clear()
    _print_header(title=title, subtitle=subtitle)

    if _is_commit_mode(options):
        _render_commits(options=options, index=index)
    else:
        _render_generic(options=options, index=index)

    print()
    keys_line = (
        _paint("Keys:", "1", "96")
        + " "
        + _paint("Up/Down", "1", "97")
        + " + Enter, "
        + _paint("Backspace", "1", "97")
        + ": previous, "
        + _paint("q", "1", "97")
        + ": cancel"
    )
    print(keys_line)
    sys.stdout.flush()


def select_one[T](
    *,
    title: str,
    options: list[SelectorOption[T]],
    subtitle: str | None = None,
    initial_index: int = 0,
    allow_back: bool,
) -> SelectorResult[T]:
    if not options:
        raise ValueError("selector requires at least one option")
    if not is_interactive_terminal():
        raise RuntimeError("interactive selector requires a TTY")

    idx = max(0, min(initial_index, len(options) - 1))

    while True:
        casted: list[SelectorOption[object]] = [
            SelectorOption(value=o.value, label=o.label, detail=o.detail) for o in options
        ]
        _render(title=title, subtitle=subtitle, options=casted, index=idx)
        key = _read_key()

        if key == "up":
            idx = (idx - 1) % len(options)
            continue
        if key == "down":
            idx = (idx + 1) % len(options)
            continue
        if key == "enter":
            chosen = options[idx]
            return SelectorResult(action="select", value=chosen.value, index=idx)
        if key == "back" and allow_back:
            return SelectorResult(action="back", value=None, index=idx)
        if key == "cancel":
            return SelectorResult(action="cancel", value=None, index=idx)


def confirm_yn(*, prompt: str) -> bool:
    if not is_interactive_terminal():
        raise RuntimeError("interactive confirmation requires a TTY")

    def read_char() -> str:
        if os.name == "nt":
            import msvcrt

            return msvcrt.getwch()

        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    while True:
        _clear()
        print(_paint("Final Confirmation", "1", "93"))
        print(_paint(prompt, "1", "97"))
        print()
        print(f"{_paint('y', '1', '32')} = continue, {_paint('n', '1', '31')} = cancel")
        sys.stdout.flush()

        ch = read_char().lower()
        if ch in {"\x1b", "\x03", "n"}:
            return False
        if ch == "y":
            return True
