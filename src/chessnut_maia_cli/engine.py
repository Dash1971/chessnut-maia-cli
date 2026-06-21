# SPDX-License-Identifier: GPL-3.0-or-later

"""UCI engine integration for Maia2 and Maia3."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_ENGINE_PATHS = {
    "maia2": Path("~/chess/maia2-engine/maia2-engine.sh"),
    "maia3": Path("~/chess/maia3-engine/maia3-engine.sh"),
}


@dataclass(frozen=True)
class EngineConfig:
    name: str
    path: Path
    elo: int | None = None

    @classmethod
    def default(cls, name: str, elo: int | None = None) -> "EngineConfig":
        if name not in DEFAULT_ENGINE_PATHS:
            supported = ", ".join(sorted(DEFAULT_ENGINE_PATHS))
            raise ValueError(f"Unsupported engine {name!r}. Choose one of: {supported}.")
        return cls(name=name, path=DEFAULT_ENGINE_PATHS[name].expanduser(), elo=elo)


class MaiaEngine:
    """Thin async-friendly wrapper around python-chess UCI engines."""

    def __init__(self, config: EngineConfig):
        self.config = config
        self._engine = None

    async def __aenter__(self) -> "MaiaEngine":
        self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self.quit()

    def start(self) -> None:
        try:
            import chess.engine
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("Install python-chess to run Maia engines.") from exc

        if not self.config.path.exists():
            raise FileNotFoundError(f"Engine launcher not found: {self.config.path}")

        self._engine = chess.engine.SimpleEngine.popen_uci(str(self.config.path))
        if self.config.elo is not None:
            option_name = "ELO" if self.config.name == "maia2" else "Elo"
            self._engine.configure({option_name: self.config.elo})

    def play(self, board: "chess.Board", movetime_ms: int = 1000) -> "chess.Move":
        if self._engine is None:
            raise RuntimeError("Engine is not running.")

        import chess.engine

        result = self._engine.play(board, chess.engine.Limit(time=movetime_ms / 1000))
        return result.move

    def quit(self) -> None:
        if self._engine is not None:
            self._engine.quit()
            self._engine = None
