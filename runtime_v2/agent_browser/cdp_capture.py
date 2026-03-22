from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

import websocket

from runtime_v2.browser.manager import expected_url_substring_for_service


def capture_page_screenshot(
    port: int, expected_url_substring: str, output_path: Path
) -> Path:
    target = _select_page_target(port, expected_url_substring)
    payload = _cdp_command(
        target["webSocketDebuggerUrl"],
        method="Page.captureScreenshot",
        params={"format": "png"},
    )
    data = str(cast(dict[str, object], payload.get("result", {})).get("data", ""))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(data))
    return output_path


def capture_primary_image_asset(
    port: int,
    expected_url_substring: str,
    output_path: Path,
    *,
    service: str = "",
    image_url_override: str = "",
) -> tuple[Path, str]:
    target = _select_page_target(port, expected_url_substring)
    image_url = image_url_override.strip()
    if not image_url and service == "genspark":
        expression = (
            "(() => {"
            "const valid = (src) => !!src && (/^https?:/i.test(src) || /^blob:/i.test(src) || /^data:/i.test(src) || src.startsWith('/api/files/'));"
            "const sels = ['.image-generated img', '.image-grid img', '.generated-images .image-container .image-grid > img:first-child'];"
            "for (const sel of sels) { const found = document.querySelector(sel); const src = found ? (found.currentSrc || found.src || '') : ''; const width = found ? (found.naturalWidth || 0) : 0; if (valid(src) && width >= 256 && !src.includes('/manual/icons/')) return src; }"
            "const candidates = Array.from(document.images).map(img => ({src: img.currentSrc || img.src || '', w: img.naturalWidth || 0})).filter(item => valid(item.src) && item.w >= 256 && !item.src.includes('/manual/icons/')).sort((a,b) => b.w - a.w);"
            "if (candidates.length) return candidates[0].src;"
            "return '';"
            "})()"
        )
    elif service == "seaart":
        expression = (
            "(() => {"
            "const sels = ['.generate-result img', '.el-image img', 'img'];"
            "for (const sel of sels) { const found = document.querySelector(sel); const src = found ? (found.currentSrc || found.src || '') : ''; if (src && /^https?:/i.test(src)) return src; }"
            "return '';"
            "})()"
        )
    else:
        expression = (
            "(() => {"
            "const imgs = Array.from(document.images).map(img => img.currentSrc || img.src).filter(Boolean);"
            "return imgs.find(src => /^https?:/i.test(src)) || '';"
            "})()"
        )
    if not image_url:
        image_payload = _cdp_command(
            target["webSocketDebuggerUrl"],
            method="Runtime.evaluate",
            params={
                "expression": expression,
                "returnByValue": True,
            },
        )
        image_url = str(
            cast(
                dict[str, object],
                cast(dict[str, object], image_payload.get("result", {})).get(
                    "result", {}
                ),
            ).get("value", "")
        )
    if not image_url:
        raise RuntimeError("SEAART_IMAGE_URL_NOT_FOUND")
    data = _download_image_bytes(image_url, target["webSocketDebuggerUrl"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    return output_path, digest


def capture_primary_video_asset(
    port: int, expected_url_substring: str, output_path: Path, *, service: str = ""
) -> tuple[Path, str]:
    _ = service
    target = _select_page_target(port, expected_url_substring)
    expression = (
        "(() => {"
        "const selectors = ['video', 'video source'];"
        "for (const sel of selectors) {"
        "  const nodes = Array.from(document.querySelectorAll(sel));"
        "  for (const node of nodes) {"
        "    const src = node.currentSrc || node.src || node.getAttribute('src') || '';"
        "    if (src && /^https?:/i.test(src)) return src;"
        "  }"
        "}"
        "return '';"
        "})()"
    )
    video_payload = _cdp_command(
        target["webSocketDebuggerUrl"],
        method="Runtime.evaluate",
        params={
            "expression": expression,
            "returnByValue": True,
        },
    )
    video_url = str(
        cast(
            dict[str, object],
            cast(dict[str, object], video_payload.get("result", {})).get("result", {}),
        ).get("value", "")
    )
    if not video_url:
        raise RuntimeError("GEMINIGEN_VIDEO_URL_NOT_FOUND")
    data = _download_image_bytes(video_url, target["webSocketDebuggerUrl"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    return output_path, digest


def write_functional_evidence_bundle(
    *,
    workspace: Path,
    service: str,
    port: int,
    expected_url_substring: str,
    service_artifact_path: Path,
    image_url_override: str = "",
) -> dict[str, object]:
    evidence_root = workspace / "functional_evidence"
    screenshot_path = capture_page_screenshot(
        port, expected_url_substring, evidence_root / "final_screen.png"
    )
    if service == "geminigen":
        asset_path, sha256 = capture_primary_video_asset(
            port,
            expected_url_substring,
            evidence_root / service_artifact_path.name,
            service=service,
        )
    elif service == "canva":
        asset_path = capture_page_screenshot(
            port, expected_url_substring, evidence_root / service_artifact_path.name
        )
        data = asset_path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
    else:
        asset_path, sha256 = capture_primary_image_asset(
            port,
            expected_url_substring,
            evidence_root / service_artifact_path.name,
            service=service,
            image_url_override=image_url_override,
        )
    service_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    service_artifact_path.write_bytes(asset_path.read_bytes())
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "service": service,
        "port": port,
        "expected_url_substring": expected_url_substring,
        "final_screen": str(screenshot_path.resolve()),
        "downloaded_asset": str(asset_path.resolve()),
        "service_artifact_path": str(service_artifact_path.resolve()),
        "sha256": sha256,
    }
    evidence_path = evidence_root / "evidence.json"
    evidence_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return payload


def collect_browser_debug_state(
    *, port: int, expected_url_substring: str, service: str = ""
) -> dict[str, object]:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/list", timeout=10
    ) as response:
        payload = json.loads(response.read().decode("utf-8", "ignore"))
    pages = [
        cast(dict[str, object], item)
        for item in cast(list[object], payload)
        if isinstance(item, dict) and str(item.get("type", "")) == "page"
    ]
    page_summaries = [
        {
            "index": idx,
            "title": str(item.get("title", "")),
            "url": str(item.get("url", "")),
        }
        for idx, item in enumerate(pages)
    ]
    target = _select_page_target(port, expected_url_substring)
    expression = (
        "(() => {"
        "const imgs = Array.from(document.images).map((img, i) => ({index: i, src: img.currentSrc || img.src || '', width: img.naturalWidth || 0, height: img.naturalHeight || 0})).filter(item => item.src).slice(0, 20);"
        "const textarea = document.querySelector('textarea, textarea.j-search-input');"
        "const body = (document.body && document.body.innerText ? document.body.innerText : '').slice(0, 2000);"
        "return JSON.stringify({url: location.href, title: document.title, textarea: textarea ? textarea.value || '' : '', followupSent: !!window.__stage2_followup_sent, regenerateClicked: !!window.__stage2_regenerate_clicked, body, images: imgs});"
        "})()"
    )
    payload = _cdp_command(
        target["webSocketDebuggerUrl"],
        method="Runtime.evaluate",
        params={"expression": expression, "returnByValue": True},
    )
    dom_state_raw = str(
        cast(
            dict[str, object],
            cast(dict[str, object], payload.get("result", {})).get("result", {}),
        ).get("value", "")
    )
    dom_state = {}
    if dom_state_raw:
        try:
            parsed = json.loads(dom_state_raw)
            if isinstance(parsed, dict):
                dom_state = {str(key): value for key, value in parsed.items()}
        except json.JSONDecodeError:
            dom_state = {"raw": dom_state_raw}
    return {
        "service": service,
        "port": port,
        "expected_url_substring": expected_url_substring,
        "tabs": page_summaries,
        "selected_target": target,
        "dom_state": dom_state,
    }


def _select_page_target(port: int, expected_url_substring: str) -> dict[str, str]:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/list", timeout=10
    ) as response:
        payload = json.loads(response.read().decode("utf-8", "ignore"))
    pages = [
        cast(dict[str, object], item)
        for item in cast(list[object], payload)
        if isinstance(item, dict)
    ]
    if expected_url_substring == expected_url_substring_for_service("genspark"):
        for item in reversed(pages):
            if str(item.get("type", "")) != "page":
                continue
            url = str(item.get("url", ""))
            if url.startswith("https://www.genspark.ai/agents?id="):
                return {
                    "webSocketDebuggerUrl": str(item.get("webSocketDebuggerUrl", "")),
                    "url": url,
                }
    for item in pages:
        if str(item.get("type", "")) != "page":
            continue
        url = str(item.get("url", ""))
        if expected_url_substring in url or (
            expected_url_substring == expected_url_substring_for_service("genspark")
            and url.startswith("https://www.genspark.ai/agents?id=")
        ):
            return {
                "webSocketDebuggerUrl": str(item.get("webSocketDebuggerUrl", "")),
                "url": url,
            }
    raise RuntimeError("CDP_TARGET_NOT_FOUND")


def _cdp_command(
    ws_url: str, *, method: str, params: dict[str, object]
) -> dict[str, object]:
    ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
    try:
        ws.send(
            json.dumps({"id": 1, "method": method, "params": params}, ensure_ascii=True)
        )
        while True:
            response = json.loads(ws.recv())
            if response.get("id") == 1:
                return cast(dict[str, object], response)
    finally:
        ws.close()


def _download_image_bytes(image_url: str, ws_url: str) -> bytes:
    try:
        with urllib.request.urlopen(image_url, timeout=30) as response:
            return response.read()
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
    ):
        return _fetch_bytes_via_page_context(ws_url, image_url)


def _fetch_bytes_via_page_context(ws_url: str, image_url: str) -> bytes:
    expression = """
(async () => {
  const response = await fetch(%s, {credentials: 'include'});
  if (!response.ok) {
    return {ok: false, status: response.status};
  }
  const buffer = await response.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = '';
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.slice(index, index + chunkSize));
  }
  return {ok: true, base64: btoa(binary)};
})()
""" % json.dumps(image_url)
    payload = _cdp_command(
        ws_url,
        method="Runtime.evaluate",
        params={
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        },
    )
    result = cast(dict[str, object], payload.get("result", {}))
    remote_result = cast(dict[str, object], result.get("result", {}))
    value = cast(dict[str, object], remote_result.get("value", {}))
    if not bool(value.get("ok", False)):
        raise RuntimeError("AGENT_BROWSER_CAPTURE_FETCH_FAILED")
    encoded = str(value.get("base64", "")).strip()
    if not encoded:
        raise RuntimeError("AGENT_BROWSER_CAPTURE_FETCH_FAILED")
    return base64.b64decode(encoded)
