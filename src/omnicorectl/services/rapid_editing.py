"""Safe, agent-friendly RAPID editing and deployment workflows.

安全且适合智能体调用的 RAPID 编辑与部署工作流。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from omnicorectl.errors import ConfigurationError, ProtocolError, RapidBuildError
from omnicorectl.services.files import FileService
from omnicorectl.services.rapid import (
    BuildError,
    ModuleChange,
    ModuleLoadResult,
    RapidService,
)

_MODULE_DECLARATION = re.compile(r"(?im)^\s*MODULE\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_END_MODULE = re.compile(r"(?im)^\s*ENDMODULE\b")
_MAX_RWS_FORM_BYTES = 100 * 1024


@dataclass(frozen=True, slots=True)
class ModuleValidation:
    module_name: str
    encoded_bytes: int


@dataclass(frozen=True, slots=True)
class ModuleWriteResult:
    task: str
    module: str
    declared_module: str
    changed: bool
    change_count_before: int
    change_count_after: int
    built: bool
    diagnostics: tuple[BuildError, ...]


@dataclass(frozen=True, slots=True)
class ModuleDeployResult:
    task: str
    local_path: str
    remote_path: str
    module: str
    replaced: bool
    uploaded_bytes: int
    built: bool
    diagnostics: tuple[BuildError, ...]
    upload_removed: bool


class RapidEditingService:
    """Compose RWS primitives into checked edit/deploy transactions.

    将 RWS 原语组合为经过检查的编辑/部署事务。
    """

    def __init__(self, rapid: RapidService, files: FileService | None = None) -> None:
        self._rapid = rapid
        self._files = files

    def write_module(
        self,
        task: str,
        module: str,
        source: str,
        *,
        expected_change_count: int | None = None,
        build: bool = True,
        rollback_on_error: bool = True,
        allow_rename: bool = False,
    ) -> ModuleWriteResult:
        validation = validate_module_source(
            source, expected_module=None if allow_rename else module
        )
        original = self._rapid.get_module_source(task, module)
        if (
            expected_change_count is not None
            and expected_change_count != original.change_count
        ):
            raise ConfigurationError(
                f"RAPID module changed concurrently: {task}/{module} expected "
                f"change count {expected_change_count}, current value is "
                f"{original.change_count}"
            )
        if source == original.source:
            return ModuleWriteResult(
                task,
                module,
                validation.module_name,
                False,
                original.change_count,
                original.change_count,
                False,
                (),
            )

        change = self._rapid.set_module_text(
            task,
            module,
            source,
            expected_change_count=original.change_count,
        )
        current_module = change.new_module_name or module
        written = self._rapid.get_module_source(task, current_module)
        if written.source != source:
            rolled_back = self._restore_source(
                task,
                current_module,
                original.source,
                written.change_count,
                rollback_on_error=rollback_on_error,
            )
            state = (
                "the original module was restored"
                if rolled_back
                else "rollback failed or disabled"
            )
            raise ProtocolError(
                f"RAPID write readback differs from requested source for "
                f"{task}/{current_module}; {state}"
            )
        diagnostics = self._build_and_diagnose(task) if build else ()
        if diagnostics:
            self._raise_after_optional_rollback(
                task,
                current_module,
                original.source,
                diagnostics,
                current_change_count=written.change_count,
                rollback_on_error=rollback_on_error,
            )
        return _write_result(task, module, validation, change, build, diagnostics)

    def patch_module(
        self,
        task: str,
        module: str,
        *,
        replace_mode: str,
        start_row: int,
        start_column: int,
        end_row: int,
        end_column: int,
        text: str,
        query_mode: str = "Force",
        expected_change_count: int | None = None,
        build: bool = True,
        rollback_on_error: bool = True,
    ) -> ModuleWriteResult:
        original = self._rapid.get_module_source(task, module)
        if (
            expected_change_count is not None
            and expected_change_count != original.change_count
        ):
            raise ConfigurationError(
                f"RAPID module changed concurrently: {task}/{module} expected "
                f"change count {expected_change_count}, current value is "
                f"{original.change_count}"
            )
        original_validation = validate_module_source(original.source)
        change = self._rapid.set_text_range(
            task,
            module,
            replace_mode=replace_mode,
            start_row=start_row,
            start_column=start_column,
            end_row=end_row,
            end_column=end_column,
            text=text,
            query_mode=query_mode,
            expected_change_count=original.change_count,
        )
        current_module = change.new_module_name or module
        written = self._rapid.get_module_source(task, current_module)
        try:
            validate_module_source(written.source)
            if written.change_count != change.change_count_after:
                raise ProtocolError(
                    f"response change count {change.change_count_after}, "
                    f"readback {written.change_count}"
                )
        except (ConfigurationError, ProtocolError) as exc:
            rolled_back = self._restore_source(
                task,
                current_module,
                original.source,
                written.change_count,
                rollback_on_error=rollback_on_error,
            )
            state = (
                "the original module was restored"
                if rolled_back
                else "rollback failed or disabled"
            )
            raise ProtocolError(
                f"RAPID patch verification failed for {task}/{current_module}: "
                f"{exc}; {state}"
            ) from exc
        diagnostics = self._build_and_diagnose(task) if build else ()
        if diagnostics:
            self._raise_after_optional_rollback(
                task,
                current_module,
                original.source,
                diagnostics,
                current_change_count=written.change_count,
                rollback_on_error=rollback_on_error,
            )
        return _write_result(
            task, module, original_validation, change, build, diagnostics
        )

    def deploy_module(
        self,
        task: str,
        local_path: Path,
        remote_path: str,
        *,
        replace: bool = False,
        build: bool = True,
        rollback_on_error: bool = True,
        remove_upload: bool = False,
    ) -> ModuleDeployResult:
        if self._files is None:
            raise ConfigurationError("file service is required for RAPID deployment")
        source_path = local_path.expanduser().resolve()
        if not source_path.is_file():
            raise ConfigurationError(
                f"local RAPID module does not exist: {source_path}"
            )
        try:
            source = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ConfigurationError(
                f"RAPID module is not valid UTF-8: {source_path}"
            ) from exc
        validation = validate_module_source(source)

        original_source: str | None = None
        existing_names = {
            item.name.lower(): item.name for item in self._rapid.list_modules(task)
        }
        existing_name = existing_names.get(validation.module_name.lower())
        if existing_name is not None:
            if not replace:
                raise ConfigurationError(
                    f"RAPID module already exists in {task}: {existing_name}; use --replace"
                )
            original_source = self._rapid.get_module_source(task, existing_name).source

        upload = self._files.upload_file(source_path, remote_path, overwrite=True)
        loaded: ModuleLoadResult | None = None
        removed = False
        try:
            loaded = self._rapid.load_module(task, remote_path, replace=replace)
            current_name = loaded.module or validation.module_name
            loaded_source = self._rapid.get_module_source(task, current_name)
            if loaded_source.source != source:
                rolled_back = self._rollback_deploy(
                    task,
                    current_name,
                    original_source,
                    rollback_on_error=rollback_on_error,
                )
                state = (
                    "the original task state was restored"
                    if rolled_back
                    else "rollback failed or disabled"
                )
                raise ProtocolError(
                    f"deployed RAPID module readback differs from local source for "
                    f"{task}/{current_name}; {state}"
                )
            diagnostics = self._build_and_diagnose(task) if build else ()
            if diagnostics:
                rolled_back = self._rollback_deploy(
                    task,
                    current_name,
                    original_source,
                    rollback_on_error=rollback_on_error,
                )
                raise RapidBuildError(
                    _diagnostic_message(task, diagnostics, rolled_back),
                    diagnostics=_diagnostic_strings(diagnostics),
                    rolled_back=rolled_back,
                )
            return ModuleDeployResult(
                task=task,
                local_path=str(source_path),
                remote_path=remote_path,
                module=current_name,
                replaced=replace,
                uploaded_bytes=upload.bytes_written,
                built=build,
                diagnostics=diagnostics,
                upload_removed=remove_upload,
            )
        finally:
            if remove_upload:
                self._files.delete_file(remote_path)
                removed = True
            # Keep this explicit so future result extensions cannot report cleanup
            # before it happened. / 保持显式赋值，避免未来扩展过早报告清理完成。
            _ = removed

    def _rollback_deploy(
        self,
        task: str,
        current_name: str,
        original_source: str | None,
        *,
        rollback_on_error: bool,
    ) -> bool:
        if not rollback_on_error:
            return False
        if original_source is not None:
            self._rapid.set_module_text(task, current_name, original_source)
        else:
            self._rapid.unload_module(task, current_name)
        self._rapid.build_task(task)
        return not self._rapid.get_build_errors(task)

    def _build_and_diagnose(self, task: str) -> tuple[BuildError, ...]:
        self._rapid.build_task(task)
        return tuple(self._rapid.get_build_errors(task))

    def _raise_after_optional_rollback(
        self,
        task: str,
        current_module: str,
        original_source: str,
        diagnostics: tuple[BuildError, ...],
        *,
        current_change_count: int,
        rollback_on_error: bool,
    ) -> None:
        rolled_back = self._restore_source(
            task,
            current_module,
            original_source,
            current_change_count,
            rollback_on_error=rollback_on_error,
        )
        raise RapidBuildError(
            _diagnostic_message(task, diagnostics, rolled_back),
            diagnostics=_diagnostic_strings(diagnostics),
            rolled_back=rolled_back,
        )

    def _restore_source(
        self,
        task: str,
        current_module: str,
        original_source: str,
        current_change_count: int,
        *,
        rollback_on_error: bool,
    ) -> bool:
        if not rollback_on_error:
            return False
        self._rapid.set_module_text(
            task,
            current_module,
            original_source,
            expected_change_count=current_change_count,
        )
        self._rapid.build_task(task)
        return not self._rapid.get_build_errors(task)


def validate_module_source(
    source: str, *, expected_module: str | None = None
) -> ModuleValidation:
    if "\x00" in source:
        raise ConfigurationError("RAPID module source contains a NUL character")
    encoded_bytes = len(source.encode("utf-8"))
    if encoded_bytes == 0:
        raise ConfigurationError("RAPID module source cannot be empty")
    if encoded_bytes >= _MAX_RWS_FORM_BYTES:
        raise ConfigurationError(
            "RAPID module source is too large for one RWS form request "
            f"({encoded_bytes} bytes; must be below {_MAX_RWS_FORM_BYTES})"
        )
    declaration = _MODULE_DECLARATION.search(source)
    if declaration is None:
        raise ConfigurationError("RAPID source has no MODULE declaration")
    if _END_MODULE.search(source) is None:
        raise ConfigurationError("RAPID source has no ENDMODULE statement")
    module_name = declaration.group(1)
    if expected_module is not None and module_name.lower() != expected_module.lower():
        raise ConfigurationError(
            f"RAPID source declares module {module_name!r}, expected {expected_module!r}; "
            "use --allow-rename to permit a module rename"
        )
    return ModuleValidation(module_name, encoded_bytes)


def _write_result(
    task: str,
    module: str,
    validation: ModuleValidation,
    change: ModuleChange,
    built: bool,
    diagnostics: tuple[BuildError, ...],
) -> ModuleWriteResult:
    return ModuleWriteResult(
        task,
        module,
        validation.module_name,
        change.changed,
        change.change_count_before,
        change.change_count_after,
        built,
        diagnostics,
    )


def _diagnostic_strings(errors: tuple[BuildError, ...]) -> tuple[str, ...]:
    return tuple(
        f"{error.module}:{error.row}:{error.column}: {error.message}"
        for error in errors
    )


def _diagnostic_message(
    task: str, errors: tuple[BuildError, ...], rolled_back: bool
) -> str:
    state = (
        "the original module was restored"
        if rolled_back
        else "rollback failed or disabled"
    )
    details = "; ".join(_diagnostic_strings(errors))
    return f"RAPID build failed for {task}; {state}: {details}"
