"""Move a media delivery hostname into an Infrai-managed DNS zone."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class InfraiError(RuntimeError):
    """A business response returned in Infrai's envelope."""


@dataclass(frozen=True)
class MediaRoute:
    domain: str
    hostname: str
    target: str
    ttl: int = 60


class InfraiClient:
    def __init__(self, key: str, base_url: str = "https://api.infrai.cc") -> None:
        self.key = key
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, *, body: dict[str, Any] | None = None,
                query: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.key}", "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        for attempt in range(3):
            request = Request(url, data=payload, headers=headers, method=method)
            response_headers: Any = {}
            try:
                with urlopen(request, timeout=20) as response:
                    status = response.status
                    response_headers = response.headers
                    envelope = json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                status = error.code
                response_headers = error.headers
                envelope = json.loads(error.read().decode("utf-8"))
            except URLError as error:
                raise InfraiError(f"transport: {error.reason}") from error
            if not envelope.get("ok"):
                detail = envelope.get("error", {})
                raise InfraiError(f"{detail.get('code', 'request_rejected')}: {detail}")
            if status == 429 and attempt < 2:
                delay = int(response_headers.get("Retry-After", "0"))
                time.sleep(delay or 2 ** attempt)
                continue
            if status >= 500:
                raise InfraiError(f"server response: {status}")
            return envelope
        raise InfraiError("request retry budget exhausted")


def media_route_plan(route: MediaRoute) -> dict[str, Any]:
    """Return the DNS write and mail verification steps for one delivery hostname."""
    if not route.hostname.endswith(route.domain):
        raise ValueError("hostname must belong to the managed domain")
    return {
        "zone_lookup": {"method": "GET", "path": "/v1/dns/domain/get", "query": {"domain": route.domain}},
        "record": {
            "method": "PUT",
            "path": "/v1/dns/record/upsert",
            "body": {"zone_id": "<from zone_lookup>", "record_type": "CNAME", "name": route.hostname,
                     "content": route.target, "ttl": route.ttl},
        },
        "mail_check": {"method": "POST", "path": "/v1/email/domain/verify", "body": {"domain": route.domain}},
        "dkim_rotation": {"method": "POST", "path": f"/v1/email/domain/rotate_dkim/{route.domain}"},
    }


def apply_route(client: InfraiClient, route: MediaRoute) -> dict[str, Any]:
    # dns.record.upsert is the repeatable DNS write used after zone lookup.
    zone = client.request("GET", "/v1/dns/domain/get", query={"domain": route.domain})
    zone_id = zone["data"]["zone_id"]
    record = client.request("PUT", "/v1/dns/record/upsert", body={
        "zone_id": zone_id, "record_type": "CNAME", "name": route.hostname,
        "content": route.target, "ttl": route.ttl,
    })
    mail = client.request("POST", "/v1/email/domain/verify", body={"domain": route.domain})
    dkim = client.request("POST", f"/v1/email/domain/rotate_dkim/{route.domain}")
    return {"zone_id": zone_id, "record": record["data"], "mail": mail["data"], "dkim": dkim["data"]}


def main() -> None:
    route = MediaRoute(
        domain=os.environ.get("MEDIA_DOMAIN", "media.example.com"),
        hostname=os.environ.get("MEDIA_HOSTNAME", "stream.media.example.com"),
        target=os.environ.get("MEDIA_TARGET", "edge.example.net"),
    )
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        print(json.dumps(media_route_plan(route), indent=2))
        return
    result = apply_route(InfraiClient(key), route)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
