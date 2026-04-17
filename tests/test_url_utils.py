from websum_to_git.url_utils import strip_tracking_params


def test_strip_tracking_params_removes_common_tracking_keys() -> None:
    url = (
        "https://example.com/article"
        "?utm_source=telegram&id=42&fbclid=abc123&gclid=def456&lang=zh#section-1"
    )

    assert strip_tracking_params(url) == "https://example.com/article?id=42&lang=zh#section-1"
