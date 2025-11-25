from __future__ import annotations

import argparse
import logging
from pathlib import Path

from websum_to_git.bot import run_bot


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram HTML → Obsidian → GitHub Bot")
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="配置文件路径（默认: config.yaml）",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    run_bot(Path(args.config))


if __name__ == "__main__":
    main()
