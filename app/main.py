"""LGD lease automation service.

Landlord dashboard (HTTP Basic) + JSON API + PandaDoc webhook receiver.
"""
from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app import archive_storage, db
from app.auth import check_credentials, hash_password
from app.config import Landlord, User, get_settings, preload_accounts_from_postgres
from app.lease import LeaseRequest
from app.pandadoc import (
    COMPLETED_STATUS,
    PandaDocClient,
    PandaDocError,
    verify_webhook_signature,
)

# Verified against when a username does not exist, so that an unknown user and
# a wrong password are indistinguishable in both answer and timing.
DECOY_HASH = hash_password("decoy-never-matches")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("lgd")

LANDLORD_DIR = (Path(__file__).resolve().parent.parent / "landlord").resolve()
# The blank, printable lease - generated from originals/lease.md by
# print/generate_print_lease.py. Served here rather than added to
# LANDLORD_DIR so there's still exactly one copy of it on disk.
BLANK_LEASE_PATH = (
    Path(__file__).resolve().parent.parent / "print" / "lease_print.html"
).resolve()
BASIC = HTTPBasic(realm="LGD Lease Maker", auto_error=False)


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Accounts must be preloaded from Postgres (if configured) before the
    # first get_settings() call - Settings.load() is deliberately
    # synchronous and only ever reads a cache, never the network itself.
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        await preload_accounts_from_postgres(database_url)

    settings = get_settings()
    await db.init(settings.db_path)
    application.state.pandadoc = PandaDocClient(
        settings.api_key, api_base=settings.api_base
    )
    logger.info(
        "LGD lease service ready in %s mode (template %s, %d landlord(s), "
        "%d user(s))",
        settings.mode.upper(),
        settings.template_uuid,
        len(settings.landlords),
        len(settings.users),
    )
    if settings.is_sandbox:
        logger.warning(
            "SANDBOX mode: documents cost nothing and are NOT legally binding."
        )
    try:
        yield
    finally:
        await application.state.pandadoc.aclose()
        await db.close_pools()


app = FastAPI(title="LGD Lease Maker", lifespan=lifespan)


def current_user(
    credentials: HTTPBasicCredentials | None = Depends(BASIC),
) -> User:
    """HTTP Basic gate for the dashboard and its API.

    Credentials travel base64-encoded, not encrypted, so serve this behind TLS.
    """
    settings = get_settings()
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Basic realm=LGD-Lease-Maker"},
    )
    if credentials is None:
        raise unauthorized

    user = settings.user_by_username(credentials.username)
    # Verify against a decoy hash when the user is unknown, so a missing
    # username and a wrong password take the same time and give the same answer.
    expected_hash = user.password_hash if user else DECOY_HASH
    ok = check_credentials(
        credentials.username,
        credentials.password,
        expected_username=credentials.username if user else "\0",
        expected_hash=expected_hash,
    )
    if not user or not ok:
        raise unauthorized
    return user


def authorize_landlord(user: User, landlord_id: str) -> Landlord:
    """Resolve a lessor id, refusing one this user may not act for."""
    settings = get_settings()
    landlord = settings.landlord_by_id(landlord_id)
    if landlord is None:
        raise HTTPException(status_code=400, detail="Unknown landlord selected.")
    if not user.may_use_landlord(landlord_id):
        raise HTTPException(
            status_code=403,
            detail="You cannot create leases for that landlord.",
        )
    return landlord


# ---------------------------------------------------------------------------
# Landlord dashboard (static files, gated)
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse("/landlord/")


@app.get("/landlord/", include_in_schema=False)
@app.get("/landlord/{asset:path}", include_in_schema=False)
async def landlord_files(asset: str = "", _: User = Depends(current_user)):
    target = (LANDLORD_DIR / (asset or "index.html")).resolve()
    # Reject anything resolving outside the landlord directory.
    if LANDLORD_DIR not in target.parents and target != LANDLORD_DIR:
        raise HTTPException(status_code=404, detail="Not found")
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target, headers={"Cache-Control": "no-store"})


@app.get("/api/blank-lease", include_in_schema=False)
async def api_blank_lease(_: User = Depends(current_user)):
    """The blank, unsigned lease for printing or downloading.

    One route serves both dashboard buttons: opening it in a new tab is the
    "Print" button (the page has its own print CSS and an on-page Print
    button), and the "Download" button hits the same URL with an anchor
    `download` attribute, which makes the browser save it instead of
    navigating - no server-side distinction needed.
    """
    if not BLANK_LEASE_PATH.is_file():
        raise HTTPException(
            status_code=404,
            detail="Blank lease not generated yet - run "
            "print/generate_print_lease.py.",
        )
    return FileResponse(
        BLANK_LEASE_PATH, media_type="text/html", headers={"Cache-Control": "no-store"}
    )


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@app.get("/api/config")
async def api_config(user: User = Depends(current_user)) -> dict[str, Any]:
    settings = get_settings()
    return {
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "is_admin": user.is_admin,
        },
        # Only the landlords this user may act for. Emails stay server-side.
        "landlords": [
            {"id": landlord.id, "name": landlord.company}
            for landlord in settings.landlords_for(user)
        ],
        "mode": settings.mode,
        "is_sandbox": settings.is_sandbox,
        "early_payment_discount": str(settings.early_payment_discount),
        "pandadoc_sends_email": settings.pandadoc_sends_email,
    }


@app.get("/api/leases")
async def api_list_leases(user: User = Depends(current_user)) -> dict[str, Any]:
    """Admins see every lease; a landlord sees only their own."""
    settings = get_settings()
    leases = await db.list_leases(
        settings.db_path,
        landlord_id=None if user.is_admin else user.landlord_id,
    )
    return {"leases": leases}


@app.post("/api/leases/preview")
async def api_preview_lease(
    lease: LeaseRequest,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Show the filled-in values without touching PandaDoc.

    Production has a 60-document annual allowance, so this exists to catch a
    typo before it costs one of them. It is free in either mode.
    """
    settings = get_settings()
    lessor = authorize_landlord(user, lease.lessor_id)
    discount = Decimal(settings.early_payment_discount)
    recipients = lease.recipients(
        lessor_name=lessor.signer_name, lessor_email=lessor.email
    )
    return {
        "document_name": lease.document_name(),
        "tokens": lease.tokens(lessor_name=lessor.company, discount=discount),
        "recipients": [
            {
                "role": person["role"],
                "name": f"{person['first_name']} {person['last_name']}".strip(),
                "email": person["email"],
            }
            for person in recipients
        ],
    }


@app.post("/api/leases", status_code=201)
async def api_create_lease(
    lease: LeaseRequest,
    request: Request,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Create the lease in PandaDoc and return a signing link to send out."""
    settings = get_settings()
    client: PandaDocClient = request.app.state.pandadoc

    lessor = authorize_landlord(user, lease.lessor_id)
    discount = Decimal(settings.early_payment_discount)
    primary = lease.tenants[0]

    try:
        document_id = await client.create_document_from_template(
            template_uuid=settings.template_uuid,
            name=lease.document_name(),
            recipients=lease.recipients(
                lessor_name=lessor.signer_name, lessor_email=lessor.email
            ),
            tokens=lease.tokens(lessor_name=lessor.company, discount=discount),
            metadata={
                "premises": lease.premises_address[:200],
                "landlord_id": lessor.id,
            },
        )
        await client.wait_until_draft(document_id)
        await client.send_document(
            document_id,
            subject=f"Lease for {lease.premises_address}",
            message=f"Please review and sign the lease for {lease.premises_address}.",
            silent=not settings.pandadoc_sends_email,
        )

        # Prefer the hosted link: it does not expire and survives restarts.
        signing_url = await client.shared_link_for(document_id, primary.email)
        url_kind = "shared_link"
        if not signing_url:
            signing_url = await client.create_session_link(
                document_id,
                primary.email,
                lifetime=settings.session_lifetime_seconds,
            )
            url_kind = "session_link"
    except PandaDocError as exc:
        logger.error("Lease creation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    tenants = [{"name": t.full_name, "email": t.email} for t in lease.tenants]
    await db.record_lease(
        settings.db_path,
        document_id=document_id,
        document_name=lease.document_name(),
        landlord_id=lessor.id,
        lessor_name=lessor.company,
        premises_address=lease.premises_address,
        tenants=tenants,
        tenant_email=primary.email,
        signing_url=signing_url,
        signing_url_kind=url_kind,
        status="document.sent",
        monthly_rent=str(lease.monthly_rent),
        term_start=lease.term_start.isoformat(),
        term_end=lease.term_end_date.isoformat(),
        mode=settings.mode,
        created_by=user.username,
    )
    logger.info(
        "Created %s lease %s for %s (%s, by %s)",
        settings.mode, document_id, lease.premises_address,
        lessor.company, user.username,
    )

    return {
        "document_id": document_id,
        "signing_url": signing_url,
        "signing_url_kind": url_kind,
        "emailed_by_pandadoc": settings.pandadoc_sends_email,
        "tenants": tenants,
        "mode": settings.mode,
        "is_sandbox": settings.is_sandbox,
    }


# ---------------------------------------------------------------------------
# Archive of executed leases
# ---------------------------------------------------------------------------

async def archive_signed_lease(client: PandaDocClient, document_id: str) -> str | None:
    """Download the executed PDF and file it under the archive directory.

    Returns the archived filename, or None if PandaDoc is still preparing it.
    Safe to call repeatedly: an already-archived lease is left alone.
    """
    settings = get_settings()
    lease = await db.get_lease(settings.db_path, document_id)
    if lease is None:
        return None
    if lease.get("archive_file"):
        return lease["archive_file"]

    try:
        pdf = await client.download_completed_pdf(
            document_id, protected=not settings.is_sandbox
        )
    except PandaDocError as exc:
        logger.error("Could not archive %s: %s", document_id, exc)
        return None
    if pdf is None:
        return None

    filename = f"{document_id}.pdf"
    await archive_storage.save(
        settings.archive_dir, filename, pdf,
        supabase_url=settings.supabase_url, supabase_key=settings.supabase_key,
    )

    await db.record_archive(settings.db_path, document_id, filename)
    logger.info("Archived executed lease %s (%d bytes)", document_id, len(pdf))
    return filename


@app.get("/api/leases/{document_id}/document")
async def api_download_lease(
    document_id: str,
    request: Request,
    user: User = Depends(current_user),
):
    """Serve the executed PDF, fetching it from PandaDoc if not yet archived."""
    settings = get_settings()
    lease = await db.get_lease(settings.db_path, document_id)
    if lease is None:
        raise HTTPException(status_code=404, detail="No such lease.")
    if not user.is_admin and lease["landlord_id"] != user.landlord_id:
        raise HTTPException(status_code=404, detail="No such lease.")

    filename = lease.get("archive_file")
    if not filename:
        filename = await archive_signed_lease(request.app.state.pandadoc, document_id)
    if not filename:
        raise HTTPException(
            status_code=409,
            detail="The signed PDF is not ready yet. Try again shortly.",
        )

    pdf = await archive_storage.read(
        settings.archive_dir, filename,
        supabase_url=settings.supabase_url, supabase_key=settings.supabase_key,
    )
    if pdf is None:
        raise HTTPException(status_code=404, detail="Archived file is missing.")

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", lease["document_name"]).strip("-")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name or document_id}.pdf"'
        },
    )


# ---------------------------------------------------------------------------
# PandaDoc webhook
# ---------------------------------------------------------------------------

@app.post("/webhooks/pandadoc", include_in_schema=False)
async def pandadoc_webhook(request: Request,
                           background: BackgroundTasks) -> Response:
    """Receive document events. Authenticated by HMAC, not by Basic auth."""
    settings = get_settings()
    raw_body = await request.body()
    signature = request.query_params.get("signature", "")

    if not verify_webhook_signature(settings.webhook_shared_key, raw_body, signature):
        logger.warning(
            "Rejected webhook with bad signature from %s",
            request.client.host if request.client else "unknown",
        )
        return JSONResponse({"detail": "Invalid signature"}, status_code=403)

    try:
        events = await request.json()
    except ValueError:
        return JSONResponse({"detail": "Malformed JSON"}, status_code=400)
    if not isinstance(events, list):
        events = [events]

    for event in events:
        if not isinstance(event, dict):
            continue
        data = event.get("data") or {}
        document_id = data.get("id")
        if not document_id:
            continue

        name = event.get("event")
        new_status = data.get("status")
        known = True
        if new_status:
            known = await db.update_status(settings.db_path, document_id, new_status)
            if known:
                logger.info("Lease %s -> %s (%s)", document_id, new_status, name)
            else:
                logger.info("Ignoring event for unknown document %s", document_id)

        # Archive the executed PDF once it exists. Downloading here would risk
        # the 20 second webhook timeout, so it runs after the response is sent.
        if known and (
            name == "document_completed_pdf_ready"
            or new_status == COMPLETED_STATUS
        ):
            background.add_task(
                archive_signed_lease, request.app.state.pandadoc, document_id
            )

    return Response(status_code=200)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
