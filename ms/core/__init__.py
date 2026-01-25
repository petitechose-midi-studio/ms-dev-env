"""Core domain types and logic."""

from .config import Config, ConfigError, load_config
from .errors import ErrorCode
from .result import Err, Ok, Result, is_err, is_ok
from .workspace import Workspace, WorkspaceError, detect_workspace

__all__ = [
    # config
    "Config",
    "ConfigError",
    "load_config",
    # errors
    "ErrorCode",
    # result
    "Err",
    "Ok",
    "Result",
    "is_err",
    "is_ok",
    # workspace
    "Workspace",
    "WorkspaceError",
    "detect_workspace",
]
