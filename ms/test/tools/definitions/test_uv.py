from pathlib import Path
from unittest.mock import patch

from ms.core.result import Err
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode
from ms.tools.definitions.uv import UvTool
from ms.tools.http import MockHttpClient


class TestUvTool:
    def test_spec(self) -> None:
        tool = UvTool()
        assert tool.spec.id == "uv"
        assert tool.spec.name == "UV"
        assert tool.spec.required_for == frozenset({Mode.DEV})

    def test_is_system_tool(self) -> None:
        tool = UvTool()
        assert tool.is_system_tool() is True


class TestUvToolLatestVersion:
    def test_returns_error(self) -> None:
        client = MockHttpClient()
        tool = UvTool()
        result = tool.latest_version(client)
        assert isinstance(result, Err)


class TestUvToolDownloadUrl:
    def test_raises_not_implemented(self) -> None:
        tool = UvTool()
        try:
            tool.download_url("0.0.0", Platform.LINUX, Arch.X64)
            raise AssertionError("Should have raised NotImplementedError")
        except NotImplementedError as e:
            assert "system tool" in str(e).lower()


class TestUvToolBinPath:
    def test_returns_none(self) -> None:
        tool = UvTool()
        assert tool.bin_path(Path("/tools"), Platform.LINUX) is None


class TestUvToolIsInstalled:
    def test_installed_when_in_path(self) -> None:
        tool = UvTool()
        with patch("shutil.which", return_value="/usr/bin/uv"):
            assert tool.is_installed(Path("/tools"), Platform.LINUX) is True

    def test_not_installed_when_not_in_path(self) -> None:
        tool = UvTool()
        with patch("shutil.which", return_value=None):
            assert tool.is_installed(Path("/tools"), Platform.LINUX) is False


class TestUvToolSystemPath:
    def test_returns_path_when_found(self) -> None:
        tool = UvTool()
        with patch("shutil.which", return_value="/usr/bin/uv"):
            assert tool.system_path(Platform.LINUX) == Path("/usr/bin/uv")

    def test_returns_none_when_not_found(self) -> None:
        tool = UvTool()
        with patch("shutil.which", return_value=None):
            assert tool.system_path(Platform.LINUX) is None
