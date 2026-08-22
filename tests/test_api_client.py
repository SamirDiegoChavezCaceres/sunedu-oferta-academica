import pytest

from sunedu import QuotaExceeded, SuneduClient, estimate_requests
from sunedu.api_client import PAGE_SIZE_MAX


def test_estimate_requests_rounds_up():
    assert estimate_requests(0) == 0
    assert estimate_requests(1) == 1
    assert estimate_requests(1000) == 1
    assert estimate_requests(1001) == 2
    assert estimate_requests(4_100_000) == 4100


def test_page_size_is_capped():
    assert estimate_requests(2000, page_size=5000) == 2  # capped at 1000


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    """Returns pages of `page_size` rows until `total_rows` is exhausted."""

    def __init__(self, total_rows):
        self.total_rows = total_rows
        self.calls = 0

    def post(self, url, json, timeout):
        self.calls += 1
        page, size = json["page"], json["pageSize"]
        total_pages = max(1, -(-self.total_rows // size))
        start = (page - 1) * size
        count = max(0, min(size, self.total_rows - start))
        return _FakeResponse({
            "data": [{"i": start + i} for i in range(count)],
            "totalPages": total_pages,
            "totalRows": self.total_rows,
        })


def test_fetch_all_pages_through():
    client = SuneduClient(session=_FakeSession(total_rows=2500))
    rows = client.fetch_all("dataset/Buscar", page_size=PAGE_SIZE_MAX)
    assert len(rows) == 2500
    assert client.requests_made == 3  # ceil(2500 / 1000)


def test_quota_refuses_oversized_pull():
    client = SuneduClient(session=_FakeSession(total_rows=4_100_000))
    with pytest.raises(QuotaExceeded):
        client.fetch_all("postulantes/Buscar", quota=1000)
    # Only the first probing page was spent, not the whole budget.
    assert client.requests_made == 1
