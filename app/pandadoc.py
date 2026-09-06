"""Thin async client for the PandaDoc public API.

Reference: https://developers.pandadoc.com/reference/about
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Terminal statuses when waiting for a freshly created document to be editable.
DRAFT_STATUS = "document.draft"
UPLOADED_STATUS = "document.uploaded"
ERROR_STATUS = "document.error"
COMPLETED_STATUS = "document.completed"


class PandaDocError(RuntimeError):
    """Any non-success response or unusable state from PandaDoc."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def verify_webhook_signature(shared_key: str, raw_body: bytes,
                             received_signature: str) -> bool:
    """Verify a PandaDoc webhook.

    PandaDoc signs the *raw* request body with HMAC-SHA256 using the shared key
    from the Developer Dashboard, and passes the hex digest as the `signature`
    query parameter. The parsed JSON must not be used - re-serializing changes
    the bytes and the digest will not match.
    """
    if not received_signature:
        return False
    expected = hmac.new(
        shared_key.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received_signature.strip())


class PandaDocClient:
    def __init__(self, api_key: str, *, api_base: str, timeout: float = 30.0) -> None:
        self._api_base = api_base.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._api_base,
            headers={
                "Authorization": f"API-Key {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise PandaDocError(f"Could not reach PandaDoc: {exc}") from exc

        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            raise PandaDocError(
                f"PandaDoc {method} {path} failed with {response.status_code}: {payload}",
                status_code=response.status_code,
                payload=payload,
            )
        if not response.content:
            return {}
        return response.json()

    async def create_document_from_template(
        self,
        *,
        template_uuid: str,
        name: str,
        recipients: list[dict[str, Any]],
        tokens: list[dict[str, str]],
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Create a document and return its id."""
        body: dict[str, Any] = {
            "name": name,
            "template_uuid": template_uuid,
            "recipients": recipients,
            "tokens": tokens,
        }
        if metadata:
            body["metadata"] = metadata
        data = await self._request("POST", "/documents", json=body)
        document_id = data.get("id")
        if not document_id:
            raise PandaDocError("PandaDoc did not return a document id", payload=data)
        return document_id

    async def get_document(self, document_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/documents/{document_id}")

    async def get_document_details(self, document_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/documents/{document_id}/details")

    async def wait_until_draft(self, document_id: str, *, timeout: float = 45.0,
                               poll_interval: float = 1.5) -> None:
        """Block until a new document finishes processing.

        A document sits in `document.uploaded` for a few seconds after creation
        and cannot be sent until it reaches `document.draft`.
        """
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            document = await self.get_document(document_id)
            status = document.get("status")
            if status == DRAFT_STATUS:
                return
            if status == ERROR_STATUS:
                raise PandaDocError(
                    "PandaDoc failed to build the document. Check that every "
                    "template token and role name matches the template.",
                    payload=document,
                )
            if status != UPLOADED_STATUS:
                # Already sent or further along - nothing to wait for.
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise PandaDocError(
                    f"Document {document_id} stayed in {status} for {timeout:.0f}s."
                )
            await asyncio.sleep(poll_interval)

    async def send_document(self, document_id: str, *, subject: str, message: str,
                            silent: bool) -> dict[str, Any]:
        """Seal the document for signing.

        `silent=True` suppresses PandaDoc's own recipient emails, which is what
        we want when the landlord delivers the link personally.
        """
        return await self._request(
            "POST",
            f"/documents/{document_id}/send",
            json={"subject": subject, "message": message, "silent": silent},
        )

    async def shared_link_for(self, document_id: str, email: str) -> str | None:
        """Return a recipient's non-expiring hosted signing URL, if present."""
        details = await self.get_document_details(document_id)
        target = email.strip().lower()
        for recipient in details.get("recipients", []):
            if (recipient.get("email") or "").strip().lower() == target:
                link = recipient.get("shared_link")
                if link:
                    return link
            # Recipient groups nest their members.
            for member in recipient.get("members", []) or []:
                if (member.get("email") or "").strip().lower() == target:
                    link = member.get("shared_link")
                    if link:
                        return link
        return None

    async def download_completed_pdf(self, document_id: str, *,
                                     protected: bool) -> bytes | None:
        """Fetch the executed PDF. Returns None while PandaDoc is still building it.

        Completed documents come from `/download-protected`, which requires a
        production key - a sandbox key gets a 401 there, so sandbox falls back
        to the plain `/download` endpoint.
        """
        path = f"/documents/{document_id}/"
        path += "download-protected" if protected else "download"
        try:
            response = await self._client.get(path)
        except httpx.HTTPError as exc:
            raise PandaDocError(f"Could not reach PandaDoc: {exc}") from exc

        if response.status_code == 202:
            # Still being prepared; Retry-After says when to come back.
            logger.info(
                "Signed PDF for %s not ready yet (retry after %s)",
                document_id, response.headers.get("Retry-After", "?"),
            )
            return None
        if response.status_code >= 400:
            raise PandaDocError(
                f"Downloading {document_id} failed with {response.status_code}",
                status_code=response.status_code,
                payload=response.text[:500],
            )
        return response.content

    async def create_session_link(self, document_id: str, email: str,
                                  *, lifetime: int) -> str:
        """Fallback: an embedded-signing session URL. Expires after `lifetime`."""
        data = await self._request(
            "POST",
            f"/documents/{document_id}/session",
            json={"recipient": email, "lifetime": lifetime},
        )
        session_id = data.get("id")
        if not session_id:
            raise PandaDocError("PandaDoc did not return a session id", payload=data)
        return f"https://app.pandadoc.com/s/{session_id}"
