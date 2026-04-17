from textwrap import dedent

from websum_to_git.config import load_config


def test_load_config_defaults_to_defuddle_enabled_and_strip_tracking(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        dedent(
            """
            telegram:
              bot_token: "token"
            llm:
              provider: "openai"
              api_key: "key"
              model: "model"
            github:
              repo: "owner/repo"
              pat: "pat"
            """
        ).strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.defuddle.enabled is True
    assert config.defuddle.strip_tracking is True
