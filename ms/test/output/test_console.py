"""Tests for ms.output.console module."""

from __future__ import annotations

from ms.output.console import (
    ConsoleProtocol,
    MockConsole,
    OutputRecord,
    RichConsole,
    Style,
)


class TestStyle:
    """Test Style enum."""

    def test_str_conversion(self) -> None:
        assert str(Style.SUCCESS) == "success"
        assert str(Style.ERROR) == "error"
        assert str(Style.WARNING) == "warning"
        assert str(Style.INFO) == "info"
        assert str(Style.DEFAULT) == "default"

    def test_all_styles_exist(self) -> None:
        expected = {"DEFAULT", "SUCCESS", "ERROR", "WARNING", "INFO", "DIM", "BOLD", "HEADER"}
        actual = {s.name for s in Style}
        assert actual == expected


class TestMockConsole:
    """Test MockConsole for testing purposes."""

    def test_print_captures_message(self) -> None:
        console = MockConsole()
        console.print("hello")
        assert len(console.outputs) == 1
        assert console.outputs[0].message == "hello"
        assert console.outputs[0].style == Style.DEFAULT

    def test_print_with_style(self) -> None:
        console = MockConsole()
        console.print("styled", Style.SUCCESS)
        assert console.outputs[0].style == Style.SUCCESS

    def test_success(self) -> None:
        console = MockConsole()
        console.success("it worked")
        assert "OK" in console.outputs[0].message
        assert "it worked" in console.outputs[0].message
        assert console.outputs[0].style == Style.SUCCESS

    def test_error(self) -> None:
        console = MockConsole()
        console.error("something failed")
        assert "error:" in console.outputs[0].message
        assert "something failed" in console.outputs[0].message
        assert console.outputs[0].style == Style.ERROR

    def test_warning(self) -> None:
        console = MockConsole()
        console.warning("be careful")
        assert "warning:" in console.outputs[0].message
        assert "be careful" in console.outputs[0].message
        assert console.outputs[0].style == Style.WARNING

    def test_info(self) -> None:
        console = MockConsole()
        console.info("fyi")
        assert "info:" in console.outputs[0].message
        assert "fyi" in console.outputs[0].message
        assert console.outputs[0].style == Style.INFO

    def test_header(self) -> None:
        console = MockConsole()
        console.header("Section Title")
        assert console.outputs[0].message == "Section Title"
        assert console.outputs[0].style == Style.HEADER

    def test_newline(self) -> None:
        console = MockConsole()
        console.newline()
        assert console.outputs[0].message == ""

    def test_clear(self) -> None:
        console = MockConsole()
        console.print("one")
        console.print("two")
        assert len(console.outputs) == 2
        console.clear()
        assert len(console.outputs) == 0

    def test_messages_property(self) -> None:
        console = MockConsole()
        console.print("one")
        console.print("two")
        assert console.messages == ["one", "two"]

    def test_text_property(self) -> None:
        console = MockConsole()
        console.print("line1")
        console.print("line2")
        assert console.text == "line1\nline2"

    def test_has_error(self) -> None:
        console = MockConsole()
        assert console.has_error() is False
        console.error("oops")
        assert console.has_error() is True

    def test_has_warning(self) -> None:
        console = MockConsole()
        assert console.has_warning() is False
        console.warning("hmm")
        assert console.has_warning() is True

    def test_has_success(self) -> None:
        console = MockConsole()
        assert console.has_success() is False
        console.success("yay")
        assert console.has_success() is True

    def test_find(self) -> None:
        console = MockConsole()
        console.print("hello world")
        console.print("hello there")
        console.print("goodbye")
        matches = console.find("hello")
        assert len(matches) == 2
        assert all("hello" in m.message for m in matches)

    def test_count(self) -> None:
        console = MockConsole()
        console.error("e1")
        console.error("e2")
        console.success("s1")
        console.print("plain")
        assert console.count(Style.ERROR) == 2
        assert console.count(Style.SUCCESS) == 1
        assert console.count(Style.DEFAULT) == 1


class TestOutputRecord:
    """Test OutputRecord dataclass."""

    def test_create(self) -> None:
        record = OutputRecord("msg", Style.SUCCESS)
        assert record.message == "msg"
        assert record.style == Style.SUCCESS

    def test_equality(self) -> None:
        r1 = OutputRecord("msg", Style.ERROR)
        r2 = OutputRecord("msg", Style.ERROR)
        assert r1 == r2


class TestRichConsole:
    """Test RichConsole integration."""

    def test_can_instantiate(self) -> None:
        """RichConsole should be instantiable."""
        console = RichConsole()
        assert console is not None

    def test_implements_protocol(self) -> None:
        """RichConsole should satisfy ConsoleProtocol."""
        console = RichConsole()
        # Check that it has all the required methods
        assert hasattr(console, "print")
        assert hasattr(console, "success")
        assert hasattr(console, "error")
        assert hasattr(console, "warning")
        assert hasattr(console, "info")
        assert hasattr(console, "header")
        assert hasattr(console, "newline")


class TestConsoleProtocol:
    """Test that protocol is properly defined."""

    def test_mock_satisfies_protocol(self) -> None:
        """MockConsole should satisfy ConsoleProtocol."""

        def use_console(c: ConsoleProtocol) -> None:
            c.print("test")
            c.success("ok")
            c.error("err")
            c.warning("warn")
            c.info("info")
            c.header("hdr")
            c.newline()

        mock = MockConsole()
        use_console(mock)  # Should not raise
        assert len(mock.outputs) == 7

    def test_rich_satisfies_protocol(self) -> None:
        """RichConsole should satisfy ConsoleProtocol at type level."""

        def accept_console(_c: ConsoleProtocol) -> bool:
            return True

        # This verifies the type compatibility
        rich = RichConsole()
        assert accept_console(rich)


class TestMultipleMessages:
    """Test scenarios with multiple messages."""

    def test_sequence_of_outputs(self) -> None:
        console = MockConsole()
        console.header("Build")
        console.info("Compiling...")
        console.success("Compiled")
        console.warning("Deprecated API used")
        console.error("Tests failed")

        assert len(console.outputs) == 5
        assert console.outputs[0].style == Style.HEADER
        assert console.outputs[1].style == Style.INFO
        assert console.outputs[2].style == Style.SUCCESS
        assert console.outputs[3].style == Style.WARNING
        assert console.outputs[4].style == Style.ERROR

    def test_mixed_print_and_shortcuts(self) -> None:
        console = MockConsole()
        console.print("plain message")
        console.print("bold message", Style.BOLD)
        console.success("done")

        assert console.count(Style.DEFAULT) == 1
        assert console.count(Style.BOLD) == 1
        assert console.count(Style.SUCCESS) == 1
