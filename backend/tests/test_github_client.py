import pytest

from app.services.github_client import GitHubClient


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("fastapi/fastapi", "fastapi/fastapi"),
        ("https://github.com/fastapi/fastapi", "fastapi/fastapi"),
        ("https://github.com/fastapi/fastapi.git", "fastapi/fastapi"),
    ],
)
def test_normalize_repository(value, expected):
    assert GitHubClient.normalize_repository(value) == expected


def test_rejects_invalid_repository():
    with pytest.raises(ValueError):
        GitHubClient.normalize_repository("just-one-part")
