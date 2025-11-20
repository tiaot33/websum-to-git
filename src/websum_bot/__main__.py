"""CLI entrypoint for the Telegram summarizer bot."""

import logging
import pathlib
import sys

try:
    from .bot import create_application
    from .config import BotConfig
except ImportError:
    # Allow execution via `python ./src/websum_bot/__main__.py` by adding src to path.
    ROOT = pathlib.Path(__file__).resolve().parents[1]
    sys.path.append(str(ROOT))
    from websum_bot.bot import create_application
    from websum_bot.config import BotConfig


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    config = BotConfig.load()
    app = create_application(config)
    app.run_polling()


if __name__ == "__main__":
    main()
