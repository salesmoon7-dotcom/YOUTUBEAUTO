from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2 import circuit_breaker, recovery_policy, retry_budget
from runtime_v2.config import RuntimeConfig
from runtime_v2.contracts.job_contract import JobContract, build_explicit_job_contract
from runtime_v2.control_plane import run_control_loop_once, seed_control_job
from runtime_v2.latest_run import load_joined_latest_run
from runtime_v2.queue_store import QueueStore, QueueStoreError


def _runtime_config(root: Path) -> RuntimeConfig:
    return RuntimeConfig.from_root(root)


class RuntimeV2ControlPlaneChainTests(unittest.TestCase):
    def test_control_plane_queue_helpers_share_queue_store_canonical_path(self) -> None:
        import runtime_v2.control_plane as control_plane_module

        self.assertIs(control_plane_module._load_jobs, QueueStore.load)
        self.assertIs(control_plane_module._save_jobs, QueueStore.save)
        self.assertIs(control_plane_module._upsert_job, QueueStore.upsert)

    def test_queue_store_load_fail_closes_on_corrupted_queue_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            queue_file = Path(tmp_dir) / "job_queue.json"
            _ = queue_file.write_text("{not-json", encoding="utf-8")

            with self.assertRaises(QueueStoreError):
                _ = QueueStore(queue_file).load()

    def test_control_plane_reports_invalid_queue_store_as_failed(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            config.queue_store_file.parent.mkdir(parents=True, exist_ok=True)
            _ = config.queue_store_file.write_text("{not-json", encoding="utf-8")

            result = run_control_loop_once(
                owner="runtime_v2", config=config, run_id="control-run-invalid-queue"
            )
            latest_join = load_joined_latest_run(config, completed=True)
            result_metadata = cast(dict[object, object], latest_join["result_metadata"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "QUEUE_STORE_INVALID")
        self.assertEqual(str(result_metadata["code"]), "QUEUE_STORE_INVALID")

    def test_retry_and_circuit_helpers_share_single_canonical_policy_module(
        self,
    ) -> None:
        self.assertIs(circuit_breaker.CircuitState, recovery_policy.CircuitState)
        self.assertIs(
            retry_budget.within_retry_budget, recovery_policy.within_retry_budget
        )
        self.assertIs(retry_budget.next_backoff_sec, recovery_policy.next_backoff_sec)
        self.assertIs(circuit_breaker.record_failure, recovery_policy.record_failure)
        self.assertIs(circuit_breaker.reset_circuit, recovery_policy.reset_circuit)
        self.assertIs(circuit_breaker.is_circuit_open, recovery_policy.is_circuit_open)

    def test_control_plane_runs_chatgpt_job_and_seeds_stage2_jobs_with_same_run_id(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            topic_spec: dict[str, object] = {
                "contract": "topic_spec",
                "contract_version": "1.0",
                "run_id": "chatgpt-run-1",
                "row_ref": "Sheet1!row1",
                "topic": "Bridge topic",
                "status_snapshot": "",
                "excel_snapshot_hash": "hash-1",
            }
            seed_control_job(
                JobContract(
                    job_id="chatgpt-job",
                    workload="chatgpt",
                    checkpoint_key="topic_spec:Sheet1!row1:hash-1",
                    payload={
                        "run_id": "chatgpt-run-1",
                        "row_ref": "Sheet1!row1",
                        "topic_spec": topic_spec,
                    },
                ),
                config=config,
            )

            with patch(
                "runtime_v2.control_plane.run_gated",
                side_effect=lambda **kwargs: {
                    "status": "ok",
                    "code": "OK",
                    "worker_result": kwargs["execute"](),
                },
            ):
                _ = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-chatgpt"
                )

            queue_payload = cast(
                list[object],
                json.loads(config.queue_store_file.read_text(encoding="utf-8")),
            )
            queued_items = [
                cast(dict[str, object], item)
                for item in queue_payload
                if isinstance(item, dict)
            ]
            by_job_id = {str(item["job_id"]): item for item in queued_items}
            routed_jobs = [
                item
                for item in queued_items
                if str(item.get("job_id", "")).startswith(("genspark-", "seaart-"))
            ]
            render_jobs = [
                item
                for item in queued_items
                if str(item.get("job_id", "")).startswith("render-")
            ]

        self.assertEqual(str(by_job_id["chatgpt-job"]["status"]), "completed")
        self.assertTrue(routed_jobs)
        self.assertEqual(len(render_jobs), 1)

    def test_control_plane_merges_chatgpt_video_plan_to_excel_main_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            topic_spec: dict[str, object] = {
                "contract": "topic_spec",
                "contract_version": "1.0",
                "run_id": "chatgpt-run-excel-main",
                "row_ref": "Sheet1!row1",
                "topic": "Bridge topic",
                "status_snapshot": "",
                "excel_snapshot_hash": "hash-1",
            }
            seed_control_job(
                JobContract(
                    job_id="chatgpt-excel-main",
                    workload="chatgpt",
                    checkpoint_key="topic_spec:Sheet1!row1:hash-1",
                    payload={
                        "run_id": "chatgpt-run-excel-main",
                        "row_ref": "Sheet1!row1",
                        "excel_path": str((root / "topic.xlsx").resolve()),
                        "sheet_name": "Sheet1",
                        "row_index": 0,
                        "topic_spec": topic_spec,
                    },
                ),
                config=config,
            )

            with (
                patch(
                    "runtime_v2.control_plane.merge_stage1_result",
                    return_value=True,
                ) as merge_mock,
                patch(
                    "runtime_v2.control_plane.run_gated",
                    side_effect=lambda **kwargs: {
                        "status": "ok",
                        "code": "OK",
                        "worker_result": kwargs["execute"](),
                    },
                ),
            ):
                _ = run_control_loop_once(
                    owner="runtime_v2",
                    config=config,
                    run_id="control-run-chatgpt-excel",
                )

        merge_mock.assert_called_once()
        self.assertEqual(merge_mock.call_args.kwargs["sheet_name"], "Sheet1")
        self.assertEqual(merge_mock.call_args.kwargs["row_index"], 0)

    def test_control_plane_writes_asset_manifest_for_stage1_routed_jobs(self) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            topic_spec: dict[str, object] = {
                "contract": "topic_spec",
                "contract_version": "1.0",
                "run_id": "chatgpt-run-manifest",
                "row_ref": "Sheet1!row1",
                "topic": "Bridge topic",
                "status_snapshot": "",
                "excel_snapshot_hash": "hash-1",
            }
            seed_control_job(
                JobContract(
                    job_id="chatgpt-manifest",
                    workload="chatgpt",
                    checkpoint_key="topic_spec:Sheet1!row1:hash-1",
                    payload={
                        "run_id": "chatgpt-run-manifest",
                        "row_ref": "Sheet1!row1",
                        "topic_spec": topic_spec,
                    },
                ),
                config=config,
            )

            with patch(
                "runtime_v2.control_plane.run_gated",
                side_effect=lambda **kwargs: {
                    "status": "ok",
                    "code": "OK",
                    "worker_result": kwargs["execute"](),
                },
            ):
                _ = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-manifest"
                )

            queue_payload = cast(
                list[object],
                json.loads(config.queue_store_file.read_text(encoding="utf-8")),
            )
            queued_items = [
                cast(dict[str, object], item)
                for item in queue_payload
                if isinstance(item, dict)
            ]
            render_job = next(
                item
                for item in queued_items
                if str(item.get("job_id", "")).startswith("render-")
            )
            render_payload = cast(dict[str, object], render_job["payload"])
            manifest_path = Path(str(render_payload["asset_manifest_path"]))
            manifest = cast(
                dict[str, object], json.loads(manifest_path.read_text(encoding="utf-8"))
            )
            self.assertTrue(manifest_path.exists())
            self.assertEqual(manifest["run_id"], "chatgpt-run-manifest")
            roles = cast(dict[str, object], manifest["roles"])
            self.assertTrue(
                str(roles["image_primary"])
                .replace("\\", "/")
                .endswith("images/genspark-chatgpt-run-manifest-1.png")
            )
            self.assertTrue(
                str(roles["stage2.scene_01.genspark"])
                .replace("\\", "/")
                .endswith("images/genspark-chatgpt-run-manifest-1.png")
            )
            self.assertTrue(
                str(roles["stage2.scene_02.seaart"])
                .replace("\\", "/")
                .endswith("images/seaart-chatgpt-run-manifest-2.png")
            )
            self.assertTrue(
                str(roles["voice_json"]).replace("\\", "/").endswith("voice.json")
            )

    def test_control_plane_routes_stage1_video_plan_without_worker_next_jobs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=r"D:\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            topic_spec: dict[str, object] = {
                "contract": "topic_spec",
                "contract_version": "1.0",
                "run_id": "chatgpt-run-no-next-jobs",
                "row_ref": "Sheet1!row1",
                "topic": "Bridge topic",
                "status_snapshot": "",
                "excel_snapshot_hash": "hash-1",
            }
            seed_control_job(
                JobContract(
                    job_id="chatgpt-no-next-jobs",
                    workload="chatgpt",
                    checkpoint_key="topic_spec:Sheet1!row1:hash-1",
                    payload={
                        "run_id": "chatgpt-run-no-next-jobs",
                        "row_ref": "Sheet1!row1",
                        "topic_spec": topic_spec,
                    },
                ),
                config=config,
            )

            with patch(
                "runtime_v2.control_plane.run_gated",
                side_effect=lambda **kwargs: {
                    "status": "ok",
                    "code": "OK",
                    "worker_result": {
                        **kwargs["execute"](),
                        "next_jobs": [],
                    },
                },
            ):
                _ = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-stage1-plan"
                )

            queue_payload = cast(
                list[object],
                json.loads(config.queue_store_file.read_text(encoding="utf-8")),
            )
            queued_items = [
                cast(dict[str, object], item)
                for item in queue_payload
                if isinstance(item, dict)
            ]
            routed_jobs = [
                item
                for item in queued_items
                if str(item.get("job_id", "")).startswith(("genspark-", "seaart-"))
            ]
            render_jobs = [
                item
                for item in queued_items
                if str(item.get("job_id", "")).startswith("render-")
            ]

        self.assertTrue(routed_jobs)
        self.assertEqual(len(render_jobs), 1)

    def test_runtime_config_from_root_keeps_latest_pointers_inside_temp_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)

        self.assertEqual(
            config.latest_active_run_file, root.resolve() / "latest_active_run.json"
        )
        self.assertEqual(
            config.latest_completed_run_file,
            root.resolve() / "latest_completed_run.json",
        )

    def test_control_plane_routes_declared_next_jobs_from_worker_result(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="qwen-job",
                    workload="qwen3_tts",
                    checkpoint_key="seed:qwen-job",
                    payload={"script_text": "hello", "chain_depth": 0},
                ),
                config=config,
            )

            runtime_result: dict[str, object] = {
                "status": "ok",
                "code": "OK",
                "worker_result": {
                    "status": "ok",
                    "stage": "synthesize_audio",
                    "error_code": "",
                    "retryable": False,
                    "next_jobs": [
                        build_explicit_job_contract(
                            job_id="rvc-qwen-job",
                            workload="rvc",
                            checkpoint_key="derived:rvc:qwen-job",
                            payload={
                                "source_path": "system/runtime_v2/artifacts/qwen3_tts/qwen-job/speech.wav",
                                "chain_depth": 1,
                            },
                            chain_step=1,
                            parent_job_id="qwen-job",
                        )
                    ],
                    "completion": {"state": "routed", "final_output": False},
                },
            }

            with patch(
                "runtime_v2.control_plane.run_gated", return_value=runtime_result
            ):
                _ = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-1"
                )

            queue_payload = cast(
                object, json.loads(config.queue_store_file.read_text(encoding="utf-8"))
            )
            self.assertIsInstance(queue_payload, list)
            if not isinstance(queue_payload, list):
                self.fail("queue payload missing")
            queue_items = cast(list[object], queue_payload)
            by_job_id: dict[str, dict[object, object]] = {}
            for item in queue_items:
                if isinstance(item, dict):
                    typed_item = cast(dict[object, object], item)
                    by_job_id[str(typed_item["job_id"])] = typed_item

        self.assertEqual(str(by_job_id["qwen-job"]["status"]), "completed")
        self.assertEqual(str(by_job_id["rvc-qwen-job"]["status"]), "queued")

    def test_control_plane_escalates_invalid_worker_result_json_and_skips_downstream_queue(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="qwen-job",
                    workload="qwen3_tts",
                    checkpoint_key="seed:qwen-job",
                    payload={"script_text": "hello", "chain_depth": 0},
                ),
                config=config,
            )
            bad_result_path = (
                root / "artifacts" / "qwen3_tts" / "qwen-job" / "result.json"
            )
            bad_result_path.parent.mkdir(parents=True, exist_ok=True)
            _ = bad_result_path.write_text("{not-json", encoding="utf-8")
            runtime_result: dict[str, object] = {
                "status": "ok",
                "code": "OK",
                "worker_result": {
                    "status": "ok",
                    "stage": "synthesize_audio",
                    "error_code": "",
                    "retryable": False,
                    "result_path": str(bad_result_path.resolve()),
                    "next_jobs": [
                        build_explicit_job_contract(
                            job_id="rvc-qwen-job",
                            workload="rvc",
                            checkpoint_key="derived:rvc:qwen-job",
                            payload={
                                "source_path": "system/runtime_v2/artifacts/qwen3_tts/qwen-job/speech.wav",
                                "chain_depth": 1,
                            },
                            chain_step=1,
                            parent_job_id="qwen-job",
                        )
                    ],
                    "completion": {"state": "routed", "final_output": False},
                },
            }

            with patch(
                "runtime_v2.control_plane.run_gated", return_value=runtime_result
            ):
                _ = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-2"
                )

            queue_payload = cast(
                list[object],
                json.loads(config.queue_store_file.read_text(encoding="utf-8")),
            )
            queue_items = [
                cast(dict[str, object], item)
                for item in queue_payload
                if isinstance(item, dict)
            ]
            latest_result = cast(
                dict[str, object],
                json.loads(config.result_router_file.read_text(encoding="utf-8")),
            )
            latest_metadata = cast(dict[str, object], latest_result["metadata"])

        self.assertEqual(len(queue_items), 1)
        self.assertEqual(str(queue_items[0]["job_id"]), "qwen-job")
        self.assertEqual(
            str(latest_metadata["worker_error_code"]), "invalid_worker_result_json"
        )

    def test_control_plane_debug_log_uses_control_run_id_not_job_id(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="qwen-job",
                    workload="qwen3_tts",
                    checkpoint_key="seed:qwen-job",
                    payload={"script_text": "hello", "chain_depth": 0},
                ),
                config=config,
            )

            runtime_result: dict[str, object] = {
                "status": "ok",
                "code": "OK",
                "worker_result": {
                    "status": "ok",
                    "stage": "synthesize_audio",
                    "error_code": "",
                    "retryable": False,
                    "next_jobs": [],
                    "completion": {
                        "state": "succeeded",
                        "final_output": True,
                        "final_artifact": "speech.wav",
                        "final_artifact_path": "system/runtime_v2/artifacts/qwen3_tts/qwen-job/speech.wav",
                    },
                },
            }

            with patch(
                "runtime_v2.control_plane.run_gated", return_value=runtime_result
            ):
                _ = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-1"
                )

            debug_log_file = config.debug_log_root / "control-run-1.jsonl"
            raw_entries = [
                json.loads(line)
                for line in debug_log_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            entries = cast(list[object], raw_entries)
            control_entries: list[dict[object, object]] = []
            for entry in entries:
                if isinstance(entry, dict):
                    typed_entry = cast(dict[object, object], entry)
                    if typed_entry.get("event") == "control_loop_result":
                        control_entries.append(typed_entry)

        self.assertEqual(len(control_entries), 1)
        self.assertEqual(str(control_entries[0]["run_id"]), "control-run-1")
        self.assertEqual(str(control_entries[0]["job_id"]), "qwen-job")

    def test_control_plane_holds_browser_blocked_job_with_fixed_backoff(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="chatgpt-blocked-job",
                    workload="chatgpt",
                    checkpoint_key="seed:chatgpt-blocked-job",
                    payload={
                        "run_id": "chatgpt-run-blocked",
                        "topic_spec": {"topic": "blocked"},
                    },
                ),
                config=config,
            )

            with patch(
                "runtime_v2.control_plane.run_gated",
                return_value={"status": "blocked", "code": "BROWSER_BLOCKED"},
            ):
                result = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-blocked"
                )

            queue_payload = cast(
                list[object],
                json.loads(config.queue_store_file.read_text(encoding="utf-8")),
            )
            queue_items = [
                cast(dict[str, object], item)
                for item in queue_payload
                if isinstance(item, dict)
            ]
            job_payload = next(
                item
                for item in queue_items
                if str(item["job_id"]) == "chatgpt-blocked-job"
            )
            latest_result = cast(
                dict[str, object],
                json.loads(config.result_router_file.read_text(encoding="utf-8")),
            )
            latest_metadata = cast(dict[str, object], latest_result["metadata"])

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["code"], "BROWSER_BLOCKED")
        self.assertEqual(str(job_payload["status"]), "retry")
        self.assertEqual(int(cast(int, job_payload["attempts"])), 0)
        self.assertGreater(float(cast(float, latest_metadata["backoff_sec"])), 0.0)
        self.assertEqual(str(latest_metadata["status"]), "blocked")
        self.assertEqual(str(latest_metadata["completion_state"]), "blocked")

    def test_control_plane_preserves_restart_exhausted_reason_in_result_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="chatgpt-restart-exhausted-job",
                    workload="chatgpt",
                    checkpoint_key="seed:chatgpt-restart-exhausted-job",
                    payload={
                        "run_id": "chatgpt-run-restart-exhausted",
                        "topic_spec": {"topic": "restart-exhausted"},
                    },
                ),
                config=config,
            )

            with patch(
                "runtime_v2.control_plane.run_gated",
                return_value={
                    "status": "blocked",
                    "code": "BROWSER_RESTART_EXHAUSTED",
                },
            ):
                result = run_control_loop_once(
                    owner="runtime_v2",
                    config=config,
                    run_id="control-run-restart-exhausted",
                )

            latest_result = cast(
                dict[str, object],
                json.loads(config.result_router_file.read_text(encoding="utf-8")),
            )
            latest_metadata = cast(dict[str, object], latest_result["metadata"])

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["code"], "BROWSER_RESTART_EXHAUSTED")
        self.assertEqual(
            str(latest_metadata["worker_error_code"]), "BROWSER_RESTART_EXHAUSTED"
        )
        self.assertEqual(str(latest_metadata["completion_state"]), "blocked")

    def test_control_plane_retries_browser_unhealthy_runtime_preflight_with_backoff(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="chatgpt-unhealthy-job",
                    workload="chatgpt",
                    checkpoint_key="seed:chatgpt-unhealthy-job",
                    payload={
                        "run_id": "chatgpt-run-unhealthy",
                        "topic_spec": {"topic": "unhealthy"},
                    },
                ),
                config=config,
            )

            with patch(
                "runtime_v2.control_plane.run_gated",
                return_value={"status": "failed", "code": "BROWSER_UNHEALTHY"},
            ):
                result = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-unhealthy"
                )

            queue_payload = cast(
                list[object],
                json.loads(config.queue_store_file.read_text(encoding="utf-8")),
            )
            queue_items = [
                cast(dict[str, object], item)
                for item in queue_payload
                if isinstance(item, dict)
            ]
            job_payload = next(
                item
                for item in queue_items
                if str(item["job_id"]) == "chatgpt-unhealthy-job"
            )
            latest_result = cast(
                dict[str, object],
                json.loads(config.result_router_file.read_text(encoding="utf-8")),
            )
            latest_metadata = cast(dict[str, object], latest_result["metadata"])
            latest_join = load_joined_latest_run(config, completed=True)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "BROWSER_UNHEALTHY")
        self.assertEqual(str(job_payload["status"]), "retry")
        self.assertEqual(int(cast(int, job_payload["attempts"])), 1)
        self.assertGreater(float(cast(float, latest_metadata["backoff_sec"])), 0.0)
        self.assertEqual(str(latest_metadata["worker_error_code"]), "BROWSER_UNHEALTHY")
        self.assertEqual(str(latest_metadata["completion_state"]), "failed")
        canonical_handoff = cast(
            dict[str, object], latest_metadata["canonical_handoff"]
        )
        self.assertEqual(str(canonical_handoff["schema_version"]), "1.0")
        self.assertEqual(str(canonical_handoff["workload"]), "chatgpt")
        self.assertFalse(bool(latest_join["out_of_sync"]))

    def test_control_plane_holds_gpt_floor_failure_with_fixed_backoff(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="chatgpt-gpt-floor-job",
                    workload="chatgpt",
                    checkpoint_key="seed:chatgpt-gpt-floor-job",
                    payload={
                        "run_id": "chatgpt-run-gpt-floor",
                        "topic_spec": {"topic": "gpt-floor"},
                    },
                ),
                config=config,
            )

            with patch(
                "runtime_v2.control_plane.run_gated",
                return_value={"status": "failed", "code": "GPT_FLOOR_FAIL"},
            ):
                result = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-gpt-floor"
                )

            queue_payload = cast(
                list[object],
                json.loads(config.queue_store_file.read_text(encoding="utf-8")),
            )
            queue_items = [
                cast(dict[str, object], item)
                for item in queue_payload
                if isinstance(item, dict)
            ]
            job_payload = next(
                item
                for item in queue_items
                if str(item["job_id"]) == "chatgpt-gpt-floor-job"
            )
            latest_result = cast(
                dict[str, object],
                json.loads(config.result_router_file.read_text(encoding="utf-8")),
            )
            latest_metadata = cast(dict[str, object], latest_result["metadata"])

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["code"], "GPT_FLOOR_FAIL")
        self.assertEqual(str(job_payload["status"]), "retry")
        self.assertEqual(int(cast(int, job_payload["attempts"])), 0)
        self.assertGreater(float(cast(float, latest_metadata["backoff_sec"])), 0.0)
        self.assertEqual(str(latest_metadata["status"]), "blocked")
        self.assertEqual(str(latest_metadata["worker_error_code"]), "GPT_FLOOR_FAIL")
        self.assertEqual(str(latest_metadata["completion_state"]), "blocked")

    def test_control_plane_holds_gpu_lease_busy_with_fixed_backoff(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="qwen-gpu-busy-job",
                    workload="qwen3_tts",
                    checkpoint_key="seed:qwen-gpu-busy-job",
                    payload={"script_text": "hello", "chain_depth": 0},
                ),
                config=config,
            )

            with patch(
                "runtime_v2.control_plane.run_gated",
                return_value={"status": "failed", "code": "GPU_LEASE_BUSY"},
            ):
                result = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-gpu-busy"
                )

            queue_payload = cast(
                list[object],
                json.loads(config.queue_store_file.read_text(encoding="utf-8")),
            )
            queue_items = [
                cast(dict[str, object], item)
                for item in queue_payload
                if isinstance(item, dict)
            ]
            job_payload = next(
                item
                for item in queue_items
                if str(item["job_id"]) == "qwen-gpu-busy-job"
            )
            latest_result = cast(
                dict[str, object],
                json.loads(config.result_router_file.read_text(encoding="utf-8")),
            )
            latest_metadata = cast(dict[str, object], latest_result["metadata"])

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["code"], "GPU_LEASE_BUSY")
        self.assertEqual(str(job_payload["status"]), "retry")
        self.assertEqual(int(cast(int, job_payload["attempts"])), 0)
        self.assertGreater(float(cast(float, latest_metadata["backoff_sec"])), 0.0)
        self.assertEqual(str(latest_metadata["status"]), "blocked")
        self.assertEqual(str(latest_metadata["worker_error_code"]), "GPU_LEASE_BUSY")
        self.assertEqual(str(latest_metadata["completion_state"]), "blocked")

    def test_control_plane_uses_retryable_not_completion_state_for_retry_decision(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="qwen-native-failed-job",
                    workload="qwen3_tts",
                    checkpoint_key="seed:qwen-native-failed-job",
                    payload={"script_text": "hello", "chain_depth": 0},
                ),
                config=config,
            )

            runtime_result: dict[str, object] = {
                "status": "ok",
                "code": "OK",
                "worker_result": {
                    "status": "failed",
                    "stage": "qwen3_tts",
                    "error_code": "native_qwen3_tts_not_implemented",
                    "retryable": False,
                    "next_jobs": [],
                    "completion": {"state": "blocked", "final_output": False},
                },
            }

            with patch(
                "runtime_v2.control_plane.run_gated", return_value=runtime_result
            ):
                result = run_control_loop_once(
                    owner="runtime_v2",
                    config=config,
                    run_id="control-run-native-failed",
                )

            queue_payload = cast(
                list[object],
                json.loads(config.queue_store_file.read_text(encoding="utf-8")),
            )
            queue_items = [
                cast(dict[str, object], item)
                for item in queue_payload
                if isinstance(item, dict)
            ]
            job_payload = next(
                item
                for item in queue_items
                if str(item["job_id"]) == "qwen-native-failed-job"
            )
            latest_result = cast(
                dict[str, object],
                json.loads(config.result_router_file.read_text(encoding="utf-8")),
            )
            latest_metadata = cast(dict[str, object], latest_result["metadata"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "native_qwen3_tts_not_implemented")
        self.assertEqual(str(job_payload["status"]), "failed")
        self.assertEqual(int(cast(int, job_payload["attempts"])), 1)
        self.assertEqual(float(cast(float, latest_metadata["backoff_sec"])), 0.0)
        self.assertEqual(
            str(latest_metadata["worker_error_code"]),
            "native_qwen3_tts_not_implemented",
        )
        self.assertEqual(str(latest_metadata["completion_state"]), "failed")

    def test_control_plane_event_log_keeps_control_run_id_on_events_and_transitions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="qwen-run-id-job",
                    workload="qwen3_tts",
                    checkpoint_key="seed:qwen-run-id-job",
                    payload={"script_text": "hello", "chain_depth": 0},
                ),
                config=config,
            )

            runtime_result: dict[str, object] = {
                "status": "ok",
                "code": "OK",
                "worker_result": {
                    "status": "ok",
                    "stage": "synthesize_audio",
                    "error_code": "",
                    "retryable": False,
                    "next_jobs": [],
                    "completion": {"state": "succeeded", "final_output": True},
                },
            }

            with patch(
                "runtime_v2.control_plane.run_gated", return_value=runtime_result
            ):
                _ = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-events"
                )

            raw_entries = [
                json.loads(line)
                for line in config.control_plane_events_file.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]
            entries = [
                cast(dict[object, object], entry)
                for entry in raw_entries
                if isinstance(entry, dict)
            ]

        job_entries = [
            entry
            for entry in entries
            if str(entry.get("job_id", "")) == "qwen-run-id-job"
        ]
        self.assertTrue(job_entries)
        self.assertTrue(
            all(
                str(entry.get("run_id", "")) == "control-run-events"
                for entry in job_entries
            )
        )

    def test_runtime_control_path_rejects_mock_chain_without_explicit_probe_or_debug_mode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="qwen-mock-runtime-job",
                    workload="qwen3_tts",
                    checkpoint_key="seed:qwen-mock-runtime-job",
                    payload={
                        "script_text": "hello",
                        "chain_depth": 0,
                        "mock_chain": True,
                    },
                ),
                config=config,
            )

            with (
                patch(
                    "runtime_v2.control_plane._run_mock_chain_worker",
                    side_effect=AssertionError("mock chain must stay probe-only"),
                ),
                patch(
                    "runtime_v2.control_plane.run_gated",
                    return_value={"status": "failed", "code": "BROWSER_UNHEALTHY"},
                ),
            ):
                result = run_control_loop_once(
                    owner="runtime_v2", config=config, run_id="control-run-no-mock"
                )

            queue_payload = cast(
                list[object],
                json.loads(config.queue_store_file.read_text(encoding="utf-8")),
            )
            queue_items = [
                cast(dict[str, object], item)
                for item in queue_payload
                if isinstance(item, dict)
            ]
            job_payload = next(
                item
                for item in queue_items
                if str(item["job_id"]) == "qwen-mock-runtime-job"
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "BROWSER_UNHEALTHY")
        self.assertEqual(str(job_payload["status"]), "retry")

    def test_control_plane_side_effect_free_mode_skips_bootstrap_and_gpt_ticks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = _runtime_config(root)
            seed_control_job(
                JobContract(
                    job_id="qwen-side-effect-free-job",
                    workload="qwen3_tts",
                    checkpoint_key="seed:qwen-side-effect-free-job",
                    payload={"script_text": "hello", "chain_depth": 0},
                ),
                config=config,
            )

            runtime_result: dict[str, object] = {
                "status": "ok",
                "code": "OK",
                "worker_result": {
                    "status": "ok",
                    "stage": "synthesize_audio",
                    "error_code": "",
                    "retryable": False,
                    "next_jobs": [],
                    "completion": {"state": "succeeded", "final_output": True},
                },
            }

            with (
                patch(
                    "runtime_v2.control_plane.ensure_runtime_bootstrap"
                ) as bootstrap_runtime,
                patch("runtime_v2.control_plane.tick_gpt_status") as tick_gpt_status,
                patch(
                    "runtime_v2.control_plane.apply_autospawn_decision"
                ) as apply_autospawn,
                patch(
                    "runtime_v2.control_plane.run_gated", return_value=runtime_result
                ),
            ):
                result = run_control_loop_once(
                    owner="runtime_v2",
                    config=config,
                    run_id="control-run-no-side-effects",
                    allow_runtime_side_effects=False,
                )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["code"], "OK")
        bootstrap_runtime.assert_not_called()
        tick_gpt_status.assert_not_called()
        apply_autospawn.assert_not_called()


if __name__ == "__main__":
    _ = unittest.main()
