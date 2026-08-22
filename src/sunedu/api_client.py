"""Quota-aware client for Peru's public SUNEDU / SIU ("Tuni") data API.

The portal exposes datasets through a single ``POST`` search endpoint whose body
is just ``{"page", "pageSize"}``. There are no server-side filters, ``pageSize``
caps at 1000, and each response carries ``{"data", "totalPages", "totalRows"}``.
Access is limited by a monthly request quota.

That quota is the reason this client exists in this shape. Some tables are far
too large to pull page-by-page within quota, so instead of silently burning the
budget the client estimates the cost up front and refuses (``QuotaExceeded``)
when a full pull would not fit, pointing you to the bulk microdata download
instead. Knowing when *not* to use the API matters as much as using it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PAGE_SIZE_MAX = 1000
DEFAULT_BASE_URL = "https://portalsiuapiexterno.tuni.pe"


class QuotaExceeded(RuntimeError):
    """Raised when a full pull would need more requests than the quota allows."""


@dataclass
class Page:
    rows: List[dict]
    total_pages: int
    total_rows: int


def estimate_requests(total_rows: int, page_size: int = PAGE_SIZE_MAX) -> int:
    """How many requests a full pull of ``total_rows`` would cost."""
    page_size = min(page_size, PAGE_SIZE_MAX)
    return math.ceil(total_rows / page_size) if total_rows > 0 else 0


def _build_session(total_retries: int) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"POST"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class SuneduClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        session: Optional[requests.Session] = None,
        timeout: float = 30.0,
        retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or _build_session(retries)
        self.timeout = timeout
        self.requests_made = 0

    def fetch_page(self, path: str, page: int, page_size: int = PAGE_SIZE_MAX) -> Page:
        """Fetch one page. ``path`` is the dataset's search endpoint path."""
        page_size = min(page_size, PAGE_SIZE_MAX)
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = self.session.post(
            url, json={"page": page, "pageSize": page_size}, timeout=self.timeout
        )
        response.raise_for_status()
        self.requests_made += 1
        body: Dict = response.json()
        return Page(
            rows=body.get("data", []),
            total_pages=int(body.get("totalPages", 0)),
            total_rows=int(body.get("totalRows", 0)),
        )

    def iter_rows(
        self,
        path: str,
        page_size: int = PAGE_SIZE_MAX,
        quota: Optional[int] = None,
    ) -> Iterator[dict]:
        """Yield every row, paging through the dataset.

        If ``quota`` is given, the full cost is checked against it after the
        first page (which reveals ``total_rows``) and :class:`QuotaExceeded` is
        raised before spending the budget on a pull that cannot finish.
        """
        first = self.fetch_page(path, page=1, page_size=page_size)
        if quota is not None:
            needed = estimate_requests(first.total_rows, page_size)
            if needed > quota:
                raise QuotaExceeded(
                    f"'{path}' has {first.total_rows:,} rows and would need "
                    f"{needed:,} requests (quota {quota:,}). Use the bulk "
                    f"microdata download for this table instead."
                )
        yield from first.rows
        for page in range(2, first.total_pages + 1):
            yield from self.fetch_page(path, page=page, page_size=page_size).rows

    def fetch_all(
        self,
        path: str,
        page_size: int = PAGE_SIZE_MAX,
        quota: Optional[int] = None,
    ) -> List[dict]:
        return list(self.iter_rows(path, page_size=page_size, quota=quota))
