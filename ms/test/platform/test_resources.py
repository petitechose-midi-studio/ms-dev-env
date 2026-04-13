from __future__ import annotations

from unittest.mock import patch

from ms.platform.resources import (
    ParallelJobSelection,
    parallel_jobs_warning,
    recommended_parallel_jobs,
    resolve_parallel_jobs,
)


def test_recommended_parallel_jobs_uses_half_physical_cores() -> None:
    with patch("ms.platform.resources.physical_cpu_count", return_value=8):
        assert recommended_parallel_jobs() == 4


def test_recommended_parallel_jobs_falls_back_to_safe_when_detection_fails() -> None:
    with patch("ms.platform.resources.physical_cpu_count", return_value=None):
        assert recommended_parallel_jobs() == 1


def test_resolve_parallel_jobs_prefers_explicit_override() -> None:
    selection = resolve_parallel_jobs(
        env={"MS_WINDOWS_NATIVE_JOBS": "12"},
        jobs_env_var="MS_WINDOWS_NATIVE_JOBS",
    )

    assert selection == ParallelJobSelection(jobs=12, source="override")


def test_resolve_parallel_jobs_ignores_invalid_override_and_uses_fastest() -> None:
    with patch("ms.platform.resources.physical_cpu_count", return_value=8):
        selection = resolve_parallel_jobs(
            env={"MS_WINDOWS_NATIVE_JOBS": "fast"},
            jobs_env_var="MS_WINDOWS_NATIVE_JOBS",
        )

    assert selection == ParallelJobSelection(jobs=4, source="physical_auto")


def test_parallel_jobs_warning_mentions_override_hint_for_fastest_mode() -> None:
    warning = parallel_jobs_warning(
        selection=ParallelJobSelection(jobs=4, source="physical_auto"),
        jobs_env_var="MS_WINDOWS_NATIVE_JOBS",
    )

    assert warning is not None
    assert "physical cores / 2" in warning
    assert "$env:MS_WINDOWS_NATIVE_JOBS='<jobs>'" in warning


def test_parallel_jobs_warning_mentions_safe_fallback() -> None:
    warning = parallel_jobs_warning(
        selection=ParallelJobSelection(jobs=1, source="safe_fallback"),
        jobs_env_var="MS_WINDOWS_NATIVE_JOBS",
    )

    assert warning is not None
    assert "falling back to safe" in warning
