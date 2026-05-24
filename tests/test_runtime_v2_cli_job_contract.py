from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_v2 import exit_codes
from runtime_v2.contracts.job_contract import build_explicit_job_contract
from runtime_v2.cli import main


class RuntimeV2CliJobContractTests(unittest.TestCase):
    def test_job_contract_path_runs_single_worker(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            runtime_root = root / "runtime"
            contract_path = root / "job.json"
            final_artifact = (
                runtime_root
                / "artifacts"
                / "chatgpt"
                / "chatgpt-boundary-job"
                / "stage1_handoff.json"
            )
            final_artifact.parent.mkdir(parents=True, exist_ok=True)
            final_artifact.write_text("handoff", encoding="utf-8")
            contract_path.write_text(
                json.dumps(
                    build_explicit_job_contract(
                        job_id="chatgpt-boundary-job",
                        workload="chatgpt",
                        checkpoint_key="boundary:chatgpt:1",
                        payload={
                            "run_id": "boundary-chatgpt-run",
                            "topic_spec": {
                                "contract": "topic_spec",
                                "contract_version": "1.0",
                                "run_id": "boundary-chatgpt-run",
                                "row_ref": "Sheet1!row1",
                                "topic": "Boundary topic",
                                "status_snapshot": "",
                                "excel_snapshot_hash": "abc123",
                                "gpt_response_text": "Title: Boundary title\n#01: scene one",
                            },
                        },
                    ),
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            with (
                patch(
                    "runtime_v2.cli.run_gated",
                    return_value={
                        "status": "ok",
                        "code": "OK",
                        "workload": "chatgpt",
                        "job": {
                            "job_id": "chatgpt-boundary-job",
                            "workload": "chatgpt",
                            "status": "completed",
                        },
                        "worker_result": {
                            "status": "ok",
                            "stage": "chatgpt",
                            "artifacts": [str(final_artifact)],
                            "manifest_path": str(root / "manifest.json"),
                            "result_path": str(root / "result.json"),
                            "error_code": "",
                            "retryable": False,
                            "details": {},
                            "next_jobs": [],
                            "completion": {
                                "state": "succeeded",
                                "final_output": True,
                                "final_artifact": "stage1_handoff.json",
                                "final_artifact_path": str(final_artifact),
                            },
                        },
                    },
                ) as run_gated_mock,
                patch(
                    "sys.argv",
                    [
                        "runtime_v2.cli",
                        "--job-contract-path",
                        str(contract_path),
                        "--runtime-root",
                        str(runtime_root),
                    ],
                ),
            ):
                exit_code = main()

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        self.assertEqual(run_gated_mock.call_count, 1)

    def test_job_contract_path_rejects_invalid_contract(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            runtime_root = root / "runtime"
            contract_path = root / "job.json"
            contract_path.write_text(
                json.dumps({"contract": "wrong"}, ensure_ascii=True),
                encoding="utf-8",
            )

            with patch(
                "sys.argv",
                [
                    "runtime_v2.cli",
                    "--job-contract-path",
                    str(contract_path),
                    "--runtime-root",
                    str(runtime_root),
                ],
            ):
                exit_code = main()

        self.assertEqual(exit_code, exit_codes.CLI_USAGE)

    def test_job_contract_path_treats_blank_success_code_as_ok(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            runtime_root = root / "runtime"
            final_artifact = (
                runtime_root
                / "artifacts"
                / "chatgpt"
                / "chatgpt-boundary-job"
                / "stage1_handoff.json"
            )
            final_artifact.parent.mkdir(parents=True, exist_ok=True)
            final_artifact.write_text("handoff", encoding="utf-8")
            contract_path = root / "job.json"
            contract_path.write_text(
                json.dumps(
                    build_explicit_job_contract(
                        job_id="chatgpt-boundary-job",
                        workload="chatgpt",
                        checkpoint_key="boundary:chatgpt:1",
                        payload={
                            "run_id": "boundary-chatgpt-run",
                            "topic_spec": {
                                "contract": "topic_spec",
                                "contract_version": "1.0",
                                "run_id": "boundary-chatgpt-run",
                                "row_ref": "Sheet1!row1",
                                "topic": "Boundary topic",
                                "status_snapshot": "",
                                "excel_snapshot_hash": "abc123",
                                "gpt_response_text": "Title: Boundary title\n#01: scene one",
                            },
                        },
                    ),
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            with (
                patch(
                    "runtime_v2.cli.run_gated",
                    return_value={
                        "status": "ok",
                        "code": "OK",
                        "workload": "chatgpt",
                        "job": {
                            "job_id": "chatgpt-boundary-job",
                            "workload": "chatgpt",
                            "status": "completed",
                        },
                        "worker_result": {
                            "status": "ok",
                            "stage": "chatgpt",
                            "artifacts": [str(final_artifact)],
                            "manifest_path": str(root / "manifest.json"),
                            "result_path": str(root / "result.json"),
                            "error_code": "",
                            "retryable": False,
                            "details": {},
                            "next_jobs": [],
                            "completion": {
                                "state": "succeeded",
                                "final_output": True,
                                "final_artifact": "stage1_handoff.json",
                                "final_artifact_path": str(final_artifact),
                            },
                        },
                    },
                ),
                patch(
                    "sys.argv",
                    [
                        "runtime_v2.cli",
                        "--job-contract-path",
                        str(contract_path),
                        "--runtime-root",
                        str(runtime_root),
                    ],
                ),
            ):
                exit_code = main()

        self.assertEqual(exit_code, exit_codes.SUCCESS)

    def test_job_contract_path_writes_cli_snapshot_artifact_metadata(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            runtime_root = root / "runtime"
            final_artifact = (
                runtime_root
                / "artifacts"
                / "chatgpt"
                / "chatgpt-boundary-job"
                / "stage1_handoff.json"
            )
            final_artifact.parent.mkdir(parents=True, exist_ok=True)
            final_artifact.write_text("handoff", encoding="utf-8")
            contract_path = root / "job.json"
            contract_path.write_text(
                json.dumps(
                    build_explicit_job_contract(
                        job_id="chatgpt-boundary-job",
                        workload="chatgpt",
                        checkpoint_key="boundary:chatgpt:1",
                        payload={
                            "run_id": "boundary-chatgpt-run",
                            "topic_spec": {
                                "contract": "topic_spec",
                                "contract_version": "1.0",
                                "run_id": "boundary-chatgpt-run",
                                "row_ref": "Sheet1!row1",
                                "topic": "Boundary topic",
                                "status_snapshot": "",
                                "excel_snapshot_hash": "abc123",
                                "gpt_response_text": "Title: Boundary title\n#01: scene one",
                            },
                        },
                    ),
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            with (
                patch(
                    "runtime_v2.cli.run_gated",
                    return_value={
                        "status": "ok",
                        "code": "OK",
                        "workload": "chatgpt",
                        "job": {
                            "job_id": "chatgpt-boundary-job",
                            "workload": "chatgpt",
                            "status": "completed",
                        },
                        "worker_result": {
                            "status": "ok",
                            "stage": "chatgpt",
                            "artifacts": [str(final_artifact)],
                            "manifest_path": str(root / "manifest.json"),
                            "result_path": str(root / "result.json"),
                            "error_code": "",
                            "retryable": False,
                            "details": {},
                            "next_jobs": [],
                            "completion": {
                                "state": "succeeded",
                                "final_output": True,
                                "final_artifact": "stage1_handoff.json",
                                "final_artifact_path": str(final_artifact),
                            },
                        },
                    },
                ),
                patch(
                    "sys.argv",
                    [
                        "runtime_v2.cli",
                        "--job-contract-path",
                        str(contract_path),
                        "--runtime-root",
                        str(runtime_root),
                    ],
                ),
            ):
                exit_code = main()

            result_router = json.loads(
                (
                    runtime_root
                    / "logs"
                    / "cli_snapshots"
                    / "boundary-chatgpt-run.result.json"
                ).read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, exit_codes.SUCCESS)
        self.assertEqual(result_router["artifacts"][0]["path"], str(final_artifact))
        canonical = result_router["metadata"]["canonical_handoff"]
        self.assertEqual(canonical["job_id"], "chatgpt-boundary-job")
        self.assertEqual(canonical["workload"], "chatgpt")

    def test_job_contract_path_updates_runtime_latest_completed_run_for_failed_worker(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            runtime_root = root / "runtime"
            contract_path = root / "job.json"
            contract_path.write_text(
                json.dumps(
                    build_explicit_job_contract(
                        job_id="canva-boundary-job",
                        workload="canva",
                        checkpoint_key="boundary:canva:3",
                        payload={
                            "run_id": "canva-boundary-run",
                            "row_ref": "Sheet1!row15",
                        },
                    ),
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )

            with (
                patch(
                    "runtime_v2.cli.run_gated",
                    return_value={
                        "status": "ok",
                        "code": "OK",
                        "workload": "canva",
                        "job": {
                            "job_id": "canva-boundary-job",
                            "workload": "canva",
                            "status": "queued",
                        },
                        "worker_result": {
                            "status": "failed",
                            "stage": "canva_adapter",
                            "manifest_path": str(root / "manifest.json"),
                            "result_path": str(root / "result.json"),
                            "error_code": "CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED",
                            "retryable": False,
                            "details": {},
                            "next_jobs": [],
                            "completion": {
                                "state": "failed",
                                "final_output": False,
                                "final_artifact": "",
                                "final_artifact_path": "",
                            },
                        },
                    },
                ),
                patch(
                    "sys.argv",
                    [
                        "runtime_v2.cli",
                        "--job-contract-path",
                        str(contract_path),
                        "--runtime-root",
                        str(runtime_root),
                    ],
                ),
            ):
                exit_code = main()

            pointer = json.loads(
                (runtime_root / "latest_completed_run.json").read_text(encoding="utf-8")
            )
            result_router = json.loads(
                (runtime_root / "evidence" / "result.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, exit_codes.CLI_USAGE)
        self.assertEqual(pointer["run_id"], "canva-boundary-run")
        self.assertEqual(pointer["status"], "failed")
        self.assertEqual(pointer["code"], "CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED")
        self.assertEqual(result_router["metadata"]["status"], "failed")
        self.assertEqual(
            result_router["metadata"]["code"],
            "CANVA_PRODUCT_BACKGROUND_CREDIT_EXHAUSTED",
        )


if __name__ == "__main__":
    _ = unittest.main()
