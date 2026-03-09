from __future__ import annotations

import re

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def parse_scalar_output(output: str) -> str:
    return output.strip()


def parse_tab_list_output(output: str) -> list[dict[str, object]]:
    tabs: list[dict[str, object]] = []
    for raw_line in output.splitlines():
        line = _ANSI_ESCAPE.sub("", raw_line).strip()
        if not line:
            continue
        if line.startswith("→"):
            line = line[1:].strip()
        if not line.startswith("["):
            continue
        close_index = line.find("]")
        if close_index <= 1:
            continue
        raw_index = line[1:close_index].strip()
        try:
            index = int(raw_index)
        except ValueError:
            continue
        remainder = line[close_index + 1 :].strip()
        separator = " - http"
        separator_index = remainder.rfind(separator)
        if separator_index == -1:
            separator = " - https"
            separator_index = remainder.rfind(separator)
        if separator_index == -1:
            continue
        title = remainder[:separator_index].strip()
        url = remainder[separator_index + 3 :].strip()
        tabs.append({"index": index, "title": title, "url": url})
    return tabs


def select_best_tab(
    tabs: list[dict[str, object]],
    *,
    expected_url_substring: str = "",
    expected_title_substring: str = "",
) -> int | None:
    best_index: int | None = None
    best_score = -1
    expected_url = expected_url_substring.strip().lower()
    expected_title = expected_title_substring.strip().lower()
    for tab in tabs:
        url = str(tab.get("url", "")).lower()
        title = str(tab.get("title", "")).lower()
        score = 0
        if expected_url and expected_url in url:
            score += 2
        if expected_title and expected_title in title:
            score += 2
        if "omnibox" in title or url.startswith("chrome://omnibox"):
            score -= 3
        raw_index = tab.get("index", 0)
        if not isinstance(raw_index, int):
            continue
        if score > best_score:
            best_score = score
            best_index = raw_index
    if best_score <= 0:
        return None
    return best_index
