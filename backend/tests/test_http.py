import httpx
import pytest

from finn.http import FetchError, HttpClient, HttpPolicy


def client(handler, **kw):
    sleeps = []
    pol = HttpPolicy(max_retries=kw.get("retries", 2), backoff_seconds=1, backoff_cap_seconds=8, min_delay_seconds=0)
    return HttpClient(pol, transport=httpx.MockTransport(handler), sleep=sleeps.append), sleeps


def test_retries_transient_then_succeeds():
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, text="ok")
    c, sleeps = client(h)
    assert c.get("https://x.invalid/a").text == "ok"
    assert len(calls) == 3 and sleeps == [1, 2]


def test_bounded_attempts():
    calls = []
    c, _ = client(lambda r: calls.append(1) or httpx.Response(500))
    with pytest.raises(FetchError) as e:
        c.get("https://x.invalid/a")
    assert len(calls) == 3 and e.value.attempts == 3 and e.value.status == 500


@pytest.mark.parametrize("code", [401, 403, 404])
def test_no_retry_and_no_workaround_on_client_errors(code):
    calls = []
    c, sleeps = client(lambda r: calls.append(1) or httpx.Response(code))
    with pytest.raises(FetchError) as e:
        c.get("https://x.invalid/a")
    assert len(calls) == 1 and e.value.status == code and sleeps == []


def test_timeout_is_retried_then_reported():
    def h(req):
        raise httpx.ReadTimeout("slow", request=req)
    c, _ = client(h, retries=1)
    with pytest.raises(FetchError) as e:
        c.get("https://x.invalid/a")
    assert e.value.kind == "timeout" and e.value.attempts == 2


def test_retry_after_respected_and_capped():
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "120"}) if len(calls) == 1 else httpx.Response(200)
    c, sleeps = client(h)
    c.get("https://x.invalid/a")
    assert sleeps == [8]


def test_politeness_delay_per_host():
    t = [0.0]
    sleeps = []
    c = HttpClient(HttpPolicy(min_delay_seconds=1.0), transport=httpx.MockTransport(lambda r: httpx.Response(200)),
                   sleep=sleeps.append, clock=lambda: t[0])
    c.get("https://a.invalid/1")
    c.get("https://a.invalid/2")
    c.get("https://b.invalid/1")
    assert sleeps == [1.0]
