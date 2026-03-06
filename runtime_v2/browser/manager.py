from __future__ import annotations


class BrowserManager:
    def __init__(self) -> None:
        self.running = False

    def start(self) -> None:
        self.running = True

    def is_healthy(self) -> bool:
        return self.running

    def restart(self) -> None:
        self.running = True

    def shutdown(self) -> None:
        self.running = False
