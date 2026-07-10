import pytest

from services.security_scan.target_validation import UnsafeTargetError, validate_public_url


@pytest.mark.parametrize("url", [
    "http://127.0.0.1",
    "http://[::1]",
    "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.1",
    "http://localhost",
    "file:///etc/passwd",
    "https://user:pass@example.com",
    "https://example.com:8443",
])
def test_rejects_non_public_targets(url):
    with pytest.raises(UnsafeTargetError):
        validate_public_url(url)


def test_accepts_public_https(monkeypatch):
    monkeypatch.setattr(
        "services.security_scan.target_validation.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    assert validate_public_url("https://example.com/path") == ("https", "example.com", 443)
