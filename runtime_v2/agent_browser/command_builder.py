from __future__ import annotations


def build_cdp_command(port: int, *args: str) -> list[str]:
    return ["agent-browser", "--cdp", str(port), *args]


def build_snapshot_command(*, port: int, max_output: int | None = None) -> list[str]:
    command = build_cdp_command(port, "snapshot", "-i")
    if max_output is not None:
        command.extend(["--max-output", str(max_output)])
    return command


def build_tab_list_command(*, port: int) -> list[str]:
    return build_cdp_command(port, "tab", "list")


def build_tab_select_command(*, port: int, index: int) -> list[str]:
    return build_cdp_command(port, "tab", str(index))


def build_get_url_command(*, port: int) -> list[str]:
    return build_cdp_command(port, "get", "url")


def build_get_title_command(*, port: int) -> list[str]:
    return build_cdp_command(port, "get", "title")


def build_eval_command(*, port: int, script: str) -> list[str]:
    return build_cdp_command(port, "eval", script)
