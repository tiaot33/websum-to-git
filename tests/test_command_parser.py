from websum_bot.command_parser import CommandOptions, parse_command_args
from websum_bot.config import BotConfig, GithubConfig, LLMConfig


def _dummy_config() -> BotConfig:
    gh = GithubConfig(token="x", default_repo="owner/repo", default_branch="main")
    llm = LLMConfig(api_key="k", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    return BotConfig(telegram_token="t", llm=llm, github=gh)


def test_parse_command_args_defaults():
    cfg = _dummy_config()
    opts = parse_command_args(["https://example.com"], cfg)
    assert isinstance(opts, CommandOptions)
    assert opts.url == "https://example.com"
    assert opts.repo == "owner/repo"
    assert opts.branch == "main"
    assert opts.filename is None


def test_parse_command_args_overrides():
    cfg = _dummy_config()
    opts = parse_command_args(
        [
            "https://example.com",
            "repo=a/b",
            "branch=dev",
            "filename=note.md",
            "tags=one,two",
            "categories=alpha",
            "keywords=key",
            "author_name=me",
            "author_email=me@example.com",
        ],
        cfg,
    )
    assert opts.repo == "a/b"
    assert opts.branch == "dev"
    assert opts.filename == "note.md"
    assert opts.tags == ["one", "two"]
    assert opts.categories == ["alpha"]
    assert opts.keywords == ["key"]
    assert opts.author_name == "me"
    assert opts.author_email == "me@example.com"

