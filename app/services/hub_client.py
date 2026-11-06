# ruff: noqa  (verbatim copy of Admin Hub's clients/python/hub_client.py; re-copy to update, do not edit)
"""Admin Hub client. Standard library only: copy this file into any Python app."""
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


class HubApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


class HubClient:
    def __init__(self, base_url: str, key: str, timeout: float = 15):
        self.base_url, self.key, self.timeout = base_url.rstrip("/"), key, timeout

    def _post(self, path: str, body: dict, headers: dict | None = None) -> dict:
        return self._request("POST", path, body, headers)

    def _request(self, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict:
        req = urllib.request.Request(
            self.base_url + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.key}", **({"Content-Type": "application/json"} if body is not None else {}), **(headers or {})},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return json.load(res)
        except urllib.error.HTTPError as e:
            err = {}
            try:
                err = json.load(e).get("error", {})
            except ValueError:
                pass
            raise HubApiError(e.code, err.get("code", "error"), err.get("message", f"Hub returned {e.code}")) from None

    def send_email(self, to: list[str], subject: str, text: str | None = None, html: str | None = None,
                   reply_to: str | None = None, from_name: str | None = None, idempotency_key: str | None = None) -> dict:
        """Pass idempotency_key (e.g. your own message id) so a retry never sends twice."""
        body = {k: v for k, v in {"to": to, "subject": subject, "text": text, "html": html, "reply_to": reply_to, "from_name": from_name}.items() if v is not None}
        return self._post("/v1/email/send", body, {"Idempotency-Key": idempotency_key} if idempotency_key else None)

    def report_metrics(self, metrics: list[dict]) -> dict:
        """Counts only, never user content. Each item: {"name", "value", optional "at": datetime or ISO string}.
        Re-sending the same name and time overwrites it, so retries are safe."""
        items = [{**m, "at": m["at"].astimezone(timezone.utc).isoformat() if isinstance(m.get("at"), datetime) else m.get("at")} for m in metrics]
        return self._post("/v1/metrics", {"metrics": [{k: v for k, v in m.items() if v is not None} for m in items]})

    def create_checkout(self, amount: int, email: str, callback_url: str, currency: str = "NGN",
                        reference: str | None = None, metadata: dict | None = None) -> dict:
        """Start a payment. amount is in minor units (250000 = NGN 2,500.00). Send the buyer to result["authorization_url"].
        Don't trust the redirect alone: wait for the signed webhook, or call get_payment. The same reference returns the same checkout."""
        body = {"amount": amount, "currency": currency, "email": email, "callback_url": callback_url, "reference": reference, "metadata": metadata}
        return self._post("/v1/payments/checkout", {k: v for k, v in body.items() if v is not None})

    def get_payment(self, payment_id: str) -> dict:
        return self._request("GET", f"/v1/payments/{urllib.parse.quote(payment_id, safe='')}")


def verify_webhook(secret: str, raw_body: bytes | str, signature_header: str | None, tolerance_seconds: int = 300) -> bool:
    """Check an event the hub sent you. Pass the RAW request body (not re-serialised JSON), the X-Hub-Signature header and your signing
    secret. Rejects tampered bodies and events older than tolerance_seconds. De-duplicate on the event id: it may arrive twice."""
    import re
    m = re.fullmatch(r"t=(\d+),v1=([0-9a-f]{64})", signature_header or "")
    if not m or abs(time.time() - int(m[1])) > tolerance_seconds:
        return False
    body = raw_body.decode() if isinstance(raw_body, bytes) else raw_body
    want = hmac.new(secret.encode(), f"{m[1]}.{body}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, m[2])
