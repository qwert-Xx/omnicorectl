from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import create_autospec

from omnicorectl.errors import ConfigurationError, ProtocolError, RapidBuildError
from omnicorectl.services.files import FileService, UploadResult
from omnicorectl.services.rapid import (
    BuildError,
    ModuleChange,
    ModuleLoadResult,
    RapidModule,
    ModuleSource,
    RapidService,
)
from omnicorectl.services.rapid_editing import (
    RapidEditingService,
    validate_module_source,
)


ORIGINAL = "MODULE MainModule\n    PROC main()\n    ENDPROC\nENDMODULE\n"
UPDATED = (
    "MODULE MainModule\n    PROC main()\n        ! updated\n    ENDPROC\nENDMODULE\n"
)


class RapidEditingTests(unittest.TestCase):
    def test_validates_module_structure_name_size_and_nul(self) -> None:
        validation = validate_module_source(ORIGINAL, expected_module="mainmodule")
        self.assertEqual(validation.module_name, "MainModule")
        with self.assertRaisesRegex(ConfigurationError, "declares module"):
            validate_module_source(ORIGINAL, expected_module="Other")
        with self.assertRaisesRegex(ConfigurationError, "ENDMODULE"):
            validate_module_source("MODULE MainModule\n")
        with self.assertRaisesRegex(ConfigurationError, "NUL"):
            validate_module_source("MODULE MainModule\n\x00\nENDMODULE\n")

    def test_write_is_noop_when_source_is_unchanged(self) -> None:
        rapid = create_autospec(RapidService, instance=True)
        rapid.get_module_source.return_value = ModuleSource(
            "T_ROB1", "MainModule", 7, len(ORIGINAL), ORIGINAL
        )
        result = RapidEditingService(rapid).write_module(
            "T_ROB1", "MainModule", ORIGINAL, expected_change_count=7
        )
        self.assertFalse(result.changed)
        rapid.set_module_text.assert_not_called()
        rapid.build_task.assert_not_called()

    def test_write_builds_and_returns_verified_result(self) -> None:
        rapid = create_autospec(RapidService, instance=True)
        rapid.get_module_source.side_effect = [
            ModuleSource("T_ROB1", "MainModule", 7, len(ORIGINAL), ORIGINAL),
            ModuleSource("T_ROB1", "MainModule", 8, len(UPDATED), UPDATED),
        ]
        rapid.set_module_text.return_value = ModuleChange(
            "T_ROB1", "MainModule", True, False, "", 7, 8
        )
        rapid.get_build_errors.return_value = []

        result = RapidEditingService(rapid).write_module(
            "T_ROB1", "MainModule", UPDATED, expected_change_count=7
        )

        self.assertTrue(result.changed)
        self.assertTrue(result.built)
        rapid.set_module_text.assert_called_once_with(
            "T_ROB1", "MainModule", UPDATED, expected_change_count=7
        )
        rapid.build_task.assert_called_once_with("T_ROB1")

    def test_build_failure_restores_original_module_and_rebuilds(self) -> None:
        rapid = create_autospec(RapidService, instance=True)
        original = ModuleSource("T_ROB1", "MainModule", 7, len(ORIGINAL), ORIGINAL)
        current = ModuleSource("T_ROB1", "MainModule", 8, len(UPDATED), UPDATED)
        rapid.get_module_source.side_effect = [original, current]
        rapid.set_module_text.side_effect = [
            ModuleChange("T_ROB1", "MainModule", True, False, "", 7, 8),
            ModuleChange("T_ROB1", "MainModule", True, False, "", 8, 9),
        ]
        error = BuildError("T_ROB1", "MainModule", 3, 9, "syntax error", "135")
        rapid.get_build_errors.side_effect = [[error], []]

        with self.assertRaises(RapidBuildError) as raised:
            RapidEditingService(rapid).write_module("T_ROB1", "MainModule", UPDATED)

        self.assertTrue(raised.exception.rolled_back)
        self.assertIn("MainModule:3:9", raised.exception.diagnostics[0])
        self.assertEqual(rapid.set_module_text.call_count, 2)
        rapid.set_module_text.assert_called_with(
            "T_ROB1", "MainModule", ORIGINAL, expected_change_count=8
        )
        self.assertEqual(rapid.build_task.call_count, 2)

    def test_write_readback_error_restores_original_module(self) -> None:
        rapid = create_autospec(RapidService, instance=True)
        rapid.get_module_source.side_effect = [
            ModuleSource("T_ROB1", "MainModule", 7, len(ORIGINAL), ORIGINAL),
            ProtocolError("temporary source file unavailable"),
        ]
        rapid.set_module_text.return_value = ModuleChange(
            "T_ROB1", "MainModule", True, False, "", 7, 8
        )
        rapid.get_build_errors.return_value = []

        with self.assertRaisesRegex(
            ProtocolError, "temporary source file unavailable.*restored"
        ):
            RapidEditingService(rapid).write_module("T_ROB1", "MainModule", UPDATED)

        rapid.set_module_text.assert_called_with(
            "T_ROB1", "MainModule", ORIGINAL, expected_change_count=8
        )
        rapid.build_task.assert_called_once_with("T_ROB1")

    def test_concurrent_change_is_rejected_before_write(self) -> None:
        rapid = create_autospec(RapidService, instance=True)
        rapid.get_module_source.return_value = ModuleSource(
            "T_ROB1", "MainModule", 9, len(ORIGINAL), ORIGINAL
        )
        with self.assertRaisesRegex(ConfigurationError, "concurrently"):
            RapidEditingService(rapid).write_module(
                "T_ROB1",
                "MainModule",
                UPDATED,
                expected_change_count=7,
            )
        rapid.set_module_text.assert_not_called()

    def test_patch_readback_mismatch_restores_original_module(self) -> None:
        rapid = create_autospec(RapidService, instance=True)
        rapid.get_module_source.side_effect = [
            ModuleSource("T_ROB1", "MainModule", 7, len(ORIGINAL), ORIGINAL),
            ModuleSource("T_ROB1", "MainModule", 9, len(UPDATED), UPDATED),
        ]
        rapid.set_text_range.return_value = ModuleChange(
            "T_ROB1", "MainModule", True, False, "", 7, 8
        )
        rapid.get_build_errors.return_value = []

        with self.assertRaisesRegex(ProtocolError, "patch verification failed"):
            RapidEditingService(rapid).patch_module(
                "T_ROB1",
                "MainModule",
                replace_mode="After",
                start_row=2,
                start_column=1,
                end_row=2,
                end_column=10,
                text="    ! comment\n",
            )

        rapid.set_module_text.assert_called_once_with(
            "T_ROB1", "MainModule", ORIGINAL, expected_change_count=9
        )
        rapid.build_task.assert_called_once_with("T_ROB1")

    def test_patch_readback_error_restores_original_module(self) -> None:
        rapid = create_autospec(RapidService, instance=True)
        rapid.get_module_source.side_effect = [
            ModuleSource("T_ROB1", "MainModule", 7, len(ORIGINAL), ORIGINAL),
            ProtocolError("temporary source file unavailable"),
        ]
        rapid.set_text_range.return_value = ModuleChange(
            "T_ROB1", "MainModule", True, False, "", 7, 8
        )
        rapid.get_build_errors.return_value = []

        with self.assertRaisesRegex(
            ProtocolError, "temporary source file unavailable.*restored"
        ):
            RapidEditingService(rapid).patch_module(
                "T_ROB1",
                "MainModule",
                replace_mode="After",
                start_row=2,
                start_column=1,
                end_row=2,
                end_column=10,
                text="    ! comment\n",
            )

        rapid.set_module_text.assert_called_with(
            "T_ROB1", "MainModule", ORIGINAL, expected_change_count=8
        )
        rapid.build_task.assert_called_once_with("T_ROB1")

    def test_deploy_uploads_loads_builds_and_removes_staging_file(self) -> None:
        rapid = create_autospec(RapidService, instance=True)
        files = create_autospec(FileService, instance=True)
        rapid.list_modules.return_value = []
        rapid.load_module.return_value = ModuleLoadResult(
            "T_ROB1", "$TEMP/MainModule.mod", "MainModule", False
        )
        rapid.get_module_source.return_value = ModuleSource(
            "T_ROB1", "MainModule", 10, len(ORIGINAL), ORIGINAL
        )
        rapid.get_build_errors.return_value = []

        with TemporaryDirectory() as directory:
            source = Path(directory) / "MainModule.mod"
            source.write_text(ORIGINAL, encoding="utf-8")
            files.upload_file.return_value = UploadResult(
                str(source), "/$TEMP/MainModule.mod", len(ORIGINAL.encode())
            )
            result = RapidEditingService(rapid, files).deploy_module(
                "T_ROB1",
                source,
                "$TEMP/MainModule.mod",
                remove_upload=True,
            )

        self.assertEqual(result.module, "MainModule")
        self.assertTrue(result.upload_removed)
        rapid.load_module.assert_called_once_with(
            "T_ROB1", "$TEMP/MainModule.mod", replace=False
        )
        rapid.build_task.assert_called_once_with("T_ROB1")
        files.delete_file.assert_called_once_with("$TEMP/MainModule.mod")

    def test_deploy_readback_mismatch_unloads_new_module_and_rebuilds(self) -> None:
        rapid = create_autospec(RapidService, instance=True)
        files = create_autospec(FileService, instance=True)
        rapid.list_modules.return_value = []
        rapid.load_module.return_value = ModuleLoadResult(
            "T_ROB1", "$TEMP/MainModule.mod", "MainModule", False
        )
        rapid.get_module_source.return_value = ModuleSource(
            "T_ROB1", "MainModule", 10, len(UPDATED), UPDATED
        )
        rapid.get_build_errors.return_value = []

        with TemporaryDirectory() as directory:
            source = Path(directory) / "MainModule.mod"
            source.write_text(ORIGINAL, encoding="utf-8")
            files.upload_file.return_value = UploadResult(
                str(source), "/$TEMP/MainModule.mod", len(ORIGINAL.encode())
            )
            with self.assertRaisesRegex(ProtocolError, "readback differs"):
                RapidEditingService(rapid, files).deploy_module(
                    "T_ROB1",
                    source,
                    "$TEMP/MainModule.mod",
                    remove_upload=True,
                )

        rapid.unload_module.assert_called_once_with("T_ROB1", "MainModule")
        rapid.build_task.assert_called_once_with("T_ROB1")
        files.delete_file.assert_called_once_with("$TEMP/MainModule.mod")

    def test_deploy_readback_error_restores_replaced_module(self) -> None:
        rapid = create_autospec(RapidService, instance=True)
        files = create_autospec(FileService, instance=True)
        rapid.list_modules.return_value = [
            RapidModule("T_ROB1", "MainModule", "ProgMod")
        ]
        rapid.get_module_source.side_effect = [
            ModuleSource("T_ROB1", "MainModule", 7, len(ORIGINAL), ORIGINAL),
            ProtocolError("temporary source file unavailable"),
        ]
        rapid.load_module.return_value = ModuleLoadResult(
            "T_ROB1", "$TEMP/MainModule.mod", "MainModule", True
        )
        rapid.get_change_count.return_value = 8
        rapid.get_build_errors.return_value = []

        with TemporaryDirectory() as directory:
            source = Path(directory) / "MainModule.mod"
            source.write_text(UPDATED, encoding="utf-8")
            files.upload_file.return_value = UploadResult(
                str(source), "/$TEMP/MainModule.mod", len(UPDATED.encode())
            )
            with self.assertRaisesRegex(
                ProtocolError, "temporary source file unavailable.*restored"
            ):
                RapidEditingService(rapid, files).deploy_module(
                    "T_ROB1",
                    source,
                    "$TEMP/MainModule.mod",
                    replace=True,
                    remove_upload=True,
                )

        rapid.set_module_text.assert_called_once_with(
            "T_ROB1", "MainModule", ORIGINAL, expected_change_count=8
        )
        rapid.build_task.assert_called_once_with("T_ROB1")
        files.delete_file.assert_called_once_with("$TEMP/MainModule.mod")

    def test_deploy_build_request_error_unloads_new_module(self) -> None:
        rapid = create_autospec(RapidService, instance=True)
        files = create_autospec(FileService, instance=True)
        rapid.list_modules.return_value = []
        rapid.load_module.return_value = ModuleLoadResult(
            "T_ROB1", "$TEMP/MainModule.mod", "MainModule", False
        )
        rapid.get_module_source.return_value = ModuleSource(
            "T_ROB1", "MainModule", 8, len(ORIGINAL), ORIGINAL
        )
        rapid.build_task.side_effect = [
            ProtocolError("build request failed"),
            None,
        ]
        rapid.get_build_errors.return_value = []

        with TemporaryDirectory() as directory:
            source = Path(directory) / "MainModule.mod"
            source.write_text(ORIGINAL, encoding="utf-8")
            files.upload_file.return_value = UploadResult(
                str(source), "/$TEMP/MainModule.mod", len(ORIGINAL.encode())
            )
            with self.assertRaisesRegex(
                ProtocolError, "build request failed.*restored"
            ):
                RapidEditingService(rapid, files).deploy_module(
                    "T_ROB1",
                    source,
                    "$TEMP/MainModule.mod",
                )

        rapid.unload_module.assert_called_once_with("T_ROB1", "MainModule")
        self.assertEqual(rapid.build_task.call_count, 2)

    def test_deploy_preserves_verification_error_when_rollback_and_cleanup_fail(
        self,
    ) -> None:
        rapid = create_autospec(RapidService, instance=True)
        files = create_autospec(FileService, instance=True)
        rapid.list_modules.return_value = []
        rapid.load_module.return_value = ModuleLoadResult(
            "T_ROB1", "$TEMP/MainModule.mod", "MainModule", False
        )
        rapid.get_module_source.side_effect = ProtocolError(
            "temporary source file unavailable"
        )
        rapid.unload_module.side_effect = ProtocolError("unload failed")
        files.delete_file.side_effect = ProtocolError("cleanup failed")

        with TemporaryDirectory() as directory:
            source = Path(directory) / "MainModule.mod"
            source.write_text(ORIGINAL, encoding="utf-8")
            files.upload_file.return_value = UploadResult(
                str(source), "/$TEMP/MainModule.mod", len(ORIGINAL.encode())
            )
            with self.assertRaisesRegex(
                ProtocolError,
                "temporary source file unavailable.*rollback failed",
            ):
                RapidEditingService(rapid, files).deploy_module(
                    "T_ROB1",
                    source,
                    "$TEMP/MainModule.mod",
                    remove_upload=True,
                )

        files.delete_file.assert_called_once_with("$TEMP/MainModule.mod")


if __name__ == "__main__":
    unittest.main()
