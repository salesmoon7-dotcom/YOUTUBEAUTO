from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from runtime_v2.config import RuntimeConfig
from runtime_v2.contracts.job_contract import JobContract, build_explicit_job_contract
from runtime_v2.control_plane import run_control_loop_once, seed_control_job


class RuntimeV2ControlPlaneChainTests(unittest.TestCase):
    def test_control_plane_runs_chatgpt_job_and_seeds_stage2_jobs_with_same_run_id(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                lease_file=root / "health" / "gpu_scheduler_health.json",
                lock_root=root / "locks",
                gui_status_file=root / "health" / "gui_status.json",
                browser_health_file=root / "health" / "browser_health.json",
                browser_registry_file=root / "health" / "browser_session_registry.json",
                gpt_status_file=root / "health" / "gpt_status.json",
                control_plane_events_file=root / "evidence" / "control_plane_events.jsonl",
                queue_store_file=root / "state" / "job_queue.json",
                feeder_state_file=root / "state" / "feeder_state.json",
                artifact_root=root / "artifacts",
                input_root=root / "inbox",
                result_router_file=root / "evidence" / "result.json",
                debug_log_root=root / "logs",
            )
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
                    payload={"run_id": "chatgpt-run-1", "row_ref": "Sheet1!row1", "topic_spec": topic_spec},
                ),
                config=config,
            )

            with patch(
                "runtime_v2.control_plane.run_gated",
                side_effect=lambda **kwargs: {"status": "ok", "code": "OK", "worker_result": kwargs["execute"]()},
            ):
                _ = run_control_loop_once(owner="runtime_v2", config=config, run_id="control-run-chatgpt")

            queue_payload = cast(list[object], json.loads(config.queue_store_file.read_text(encoding="utf-8")))
            queued_items = [cast(dict[str, object], item) for item in queue_payload if isinstance(item, dict)]
            by_job_id = {str(item["job_id"]): item for item in queued_items}
            routed_jobs = [item for item in queued_items if str(item.get("job_id", "")).startswith(("genspark-", "seaart-"))]
            render_jobs = [item for item in queued_items if str(item.get("job_id", "")).startswith("render-")]

        self.assertEqual(str(by_job_id["chatgpt-job"]["status"]), "completed")
        self.assertTrue(routed_jobs)
        self.assertEqual(len(render_jobs), 1)
        first_routed_payload = cast(dict[str, object], routed_jobs[0]["payload"])
        render_payload = cast(dict[str, object], render_jobs[0]["payload"])
        self.assertEqual(first_routed_payload["run_id"], "chatgpt-run-1")
        self.assertEqual(first_routed_payload["row_ref"], "Sheet1!row1")
        self.assertEqual(render_payload["run_id"], "chatgpt-run-1")
        self.assertEqual(render_payload["row_ref"], "Sheet1!row1")

    def test_control_plane_routes_declared_next_jobs_from_worker_result(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                lease_file=root / "health" / "gpu_scheduler_health.json",
                lock_root=root / "locks",
                gui_status_file=root / "health" / "gui_status.json",
                browser_health_file=root / "health" / "browser_health.json",
                browser_registry_file=root / "health" / "browser_session_registry.json",
                gpt_status_file=root / "health" / "gpt_status.json",
                control_plane_events_file=root / "evidence" / "control_plane_events.jsonl",
                queue_store_file=root / "state" / "job_queue.json",
                feeder_state_file=root / "state" / "feeder_state.json",
                artifact_root=root / "artifacts",
                input_root=root / "inbox",
                result_router_file=root / "evidence" / "result.json",
                debug_log_root=root / "logs",
            )
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
                            payload={"source_path": "system/runtime_v2/artifacts/qwen3_tts/qwen-job/speech.wav", "chain_depth": 1},
                            chain_step=1,
                            parent_job_id="qwen-job",
                        )
                    ],
                    "completion": {"state": "routed", "final_output": False},
                },
            }

            with patch("runtime_v2.control_plane.run_gated", return_value=runtime_result):
                _ = run_control_loop_once(owner="runtime_v2", config=config, run_id="control-run-1")

            queue_payload = cast(object, json.loads(config.queue_store_file.read_text(encoding="utf-8")))
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

    def test_control_plane_escalates_invalid_worker_result_json_and_skips_downstream_queue(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                lease_file=root / "health" / "gpu_scheduler_health.json",
                lock_root=root / "locks",
                gui_status_file=root / "health" / "gui_status.json",
                browser_health_file=root / "health" / "browser_health.json",
                browser_registry_file=root / "health" / "browser_session_registry.json",
                gpt_status_file=root / "health" / "gpt_status.json",
                control_plane_events_file=root / "evidence" / "control_plane_events.jsonl",
                queue_store_file=root / "state" / "job_queue.json",
                feeder_state_file=root / "state" / "feeder_state.json",
                artifact_root=root / "artifacts",
                input_root=root / "inbox",
                result_router_file=root / "evidence" / "result.json",
                debug_log_root=root / "logs",
            )
            seed_control_job(
                JobContract(
                    job_id="qwen-job",
                    workload="qwen3_tts",
                    checkpoint_key="seed:qwen-job",
                    payload={"script_text": "hello", "chain_depth": 0},
                ),
                config=config,
            )
            bad_result_path = root / "artifacts" / "qwen3_tts" / "qwen-job" / "result.json"
            bad_result_path.parent.mkdir(parents=True, exist_ok=True)
            bad_result_path.write_text("{not-json", encoding="utf-8")
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
                            payload={"source_path": "system/runtime_v2/artifacts/qwen3_tts/qwen-job/speech.wav", "chain_depth": 1},
                            chain_step=1,
                            parent_job_id="qwen-job",
                        )
                    ],
                    "completion": {"state": "routed", "final_output": False},
                },
            }

            with patch("runtime_v2.control_plane.run_gated", return_value=runtime_result):
                _ = run_control_loop_once(owner="runtime_v2", config=config, run_id="control-run-2")

            queue_payload = cast(list[object], json.loads(config.queue_store_file.read_text(encoding="utf-8")))
            queue_items = [cast(dict[str, object], item) for item in queue_payload if isinstance(item, dict)]
            latest_result = cast(dict[str, object], json.loads(config.result_router_file.read_text(encoding="utf-8")))
            latest_metadata = cast(dict[str, object], latest_result["metadata"])

        self.assertEqual(len(queue_items), 1)
        self.assertEqual(str(queue_items[0]["job_id"]), "qwen-job")
        self.assertEqual(str(latest_metadata["worker_error_code"]), "invalid_worker_result_json")

    def test_control_plane_debug_log_uses_control_run_id_not_job_id(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                lease_file=root / "health" / "gpu_scheduler_health.json",
                lock_root=root / "locks",
                gui_status_file=root / "health" / "gui_status.json",
                browser_health_file=root / "health" / "browser_health.json",
                browser_registry_file=root / "health" / "browser_session_registry.json",
                gpt_status_file=root / "health" / "gpt_status.json",
                control_plane_events_file=root / "evidence" / "control_plane_events.jsonl",
                queue_store_file=root / "state" / "job_queue.json",
                feeder_state_file=root / "state" / "feeder_state.json",
                artifact_root=root / "artifacts",
                input_root=root / "inbox",
                result_router_file=root / "evidence" / "result.json",
                debug_log_root=root / "logs",
            )
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
                    "completion": {"state": "succeeded", "final_output": True, "final_artifact": "speech.wav", "final_artifact_path": "system/runtime_v2/artifacts/qwen3_tts/qwen-job/speech.wav"},
                },
            }

            with patch("runtime_v2.control_plane.run_gated", return_value=runtime_result):
                _ = run_control_loop_once(owner="runtime_v2", config=config, run_id="control-run-1")

            debug_log_file = config.debug_log_root / "control-run-1.jsonl"
            raw_entries = [json.loads(line) for line in debug_log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
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

    def test_control_plane_keeps_browser_blocked_job_queued_without_consuming_attempt(self) -> None:
        with tempfile.TemporaryDirectory(dir="D:\\YOUTUBEAUTO") as tmp_dir:
            root = Path(tmp_dir)
            config = RuntimeConfig(
                lease_file=root / "health" / "gpu_scheduler_health.json",
                lock_root=root / "locks",
                gui_status_file=root / "health" / "gui_status.json",
                browser_health_file=root / "health" / "browser_health.json",
                browser_registry_file=root / "health" / "browser_session_registry.json",
                gpt_status_file=root / "health" / "gpt_status.json",
                control_plane_events_file=root / "evidence" / "control_plane_events.jsonl",
                queue_store_file=root / "state" / "job_queue.json",
                feeder_state_file=root / "state" / "feeder_state.json",
                artifact_root=root / "artifacts",
                input_root=root / "inbox",
                result_router_file=root / "evidence" / "result.json",
                debug_log_root=root / "logs",
            )
            seed_control_job(
                JobContract(
                    job_id="chatgpt-blocked-job",
                    workload="chatgpt",
                    checkpoint_key="seed:chatgpt-blocked-job",
                    payload={"run_id": "chatgpt-run-blocked", "topic_spec": {"topic": "blocked"}},
                ),
                config=config,
            )

            with patch(
                "runtime_v2.control_plane.run_gated",
                return_value={"status": "blocked", "code": "BROWSER_BLOCKED"},
            ):
                result = run_control_loop_once(owner="runtime_v2", config=config, run_id="control-run-blocked")

            queue_payload = cast(list[object], json.loads(config.queue_store_file.read_text(encoding="utf-8")))
            queue_items = [cast(dict[str, object], item) for item in queue_payload if isinstance(item, dict)]
            job_payload = next(item for item in queue_items if str(item["job_id"]) == "chatgpt-blocked-job")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], "BROWSER_BLOCKED")
        self.assertEqual(str(job_payload["status"]), "queued")
        self.assertEqual(int(cast(int, job_payload["attempts"])), 0)


if __name__ == "__main__":
    _ = unittest.main()
