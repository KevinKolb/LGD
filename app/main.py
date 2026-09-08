"""LGD web service.

Serves the static pages and the printable blank lease, plus a small JSON
API behind HTTP Basic for the manager and admin areas. Accounts and the
application/notice/news records live in Supabase Postgres when configured,
and on local disk otherwise - see app/config.py and app/db.py.
"""
from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from app import accounts, db
from app.accounts import MIN_PASSWORD_LENGTH
from app.auth import check_credentials, hash_password, verify_password
from app.config import (
    ConfigError,
    Landlord,
    ROLE_RESIDENT,
    User,
    get_settings,
    preload_accounts_from_postgres,
)
from app.tenant_portal import ApplicationRequest, NewsRequest, NoticeRequest

# Verified against when a username does not exist, so that an unknown user and
# a wrong password are indistinguishable in both answer and timing.
DECOY_HASH = hash_password("decoy-never-matches")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("lgd")

MANAGER_DIR = (Path(__file__).resolve().parent.parent / "manager").resolve()
ADMIN_DIR = (Path(__file__).resolve().parent.parent / "admin").resolve()
SHARED_DIR = (Path(__file__).resolve().parent.parent / "shared").resolve()
PRINT_DIR = (Path(__file__).resolve().parent.parent / "print").resolve()
RESIDENT_DIR = (Path(__file__).resolve().parent.parent / "resident").resolve()
APPLICANT_DIR = (Path(__file__).resolve().parent.parent / "applicant").resolve()
FAVICON_PATH = (Path(__file__).resolve().parent.parent / "favicon.ico").resolve()
ROOT_INDEX_PATH = (Path(__file__).resolve().parent.parent / "index.html").resolve()
# The blank, printable lease - generated from documents/lease.md by
# print/generate_print_lease.py. Served here rather than added to
# MANAGER_DIR so there's still exactly one copy of it on disk.
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
    logger.info(
        "LGD service ready (%d landlord(s), %d user(s))",
        len(settings.landlords),
        len(settings.users),
    )
    try:
        yield
    finally:
        await db.close_pools()


app = FastAPI(title="LGD", lifespan=lifespan)


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


def require_not_resident(user: User) -> None:
    """Keep resident accounts out of the manager dashboard and its API - a
    resident only ever needs /api/notices and /api/account/password."""
    if user.is_resident:
        raise HTTPException(status_code=404, detail="Not found")


def resolve_static_file(base_dir: Path, asset: str) -> Path:
    """Resolve `asset` under `base_dir`, defaulting to its index.html -
    shared by the manager, admin, and resident static file routes."""
    target = (base_dir / (asset or "index.html")).resolve()
    if base_dir not in target.parents and target != base_dir:
        raise HTTPException(status_code=404, detail="Not found")
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return target


def authorize_landlord(user: User, landlord_id: str) -> Landlord:
    """Resolve a lessor id, refusing one this user may not act for."""
    settings = get_settings()
    landlord = settings.landlord_by_id(landlord_id)
    if landlord is None:
        raise HTTPException(status_code=400, detail="Unknown landlord selected.")
    if not user.may_use_landlord(landlord_id):
        raise HTTPException(
            status_code=403,
            detail="You cannot act for that landlord.",
        )
    return landlord


# ---------------------------------------------------------------------------
# Manager dashboard (static files, gated)
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    """A small public hub page - no login needed, just links to the three
    areas (each of which enforces its own auth downstream)."""
    return FileResponse(ROOT_INDEX_PATH, headers={"Cache-Control": "no-store"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Public - browsers request this at the bare domain root regardless of
    any <link rel="icon"> tag, before any login context exists."""
    if not FAVICON_PATH.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(FAVICON_PATH, media_type="image/vnd.microsoft.icon")


@app.get("/print/{asset:path}", include_in_schema=False)
async def print_files(asset: str, user: User = Depends(current_user)):
    """The blank paper lease, at the same relative path it has on GitHub
    Pages (../print/lease_print.html from the manager page), so one href
    works on both hosts. /api/blank-lease still serves the same file."""
    require_not_resident(user)
    return FileResponse(
        resolve_static_file(PRINT_DIR, asset),
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/shared/{asset:path}", include_in_schema=False)
async def shared_files(asset: str):
    """The stylesheet and footer every page loads. Public, because the
    applicant, tenant, and hub pages that load it are public too."""
    return FileResponse(
        resolve_static_file(SHARED_DIR, asset), headers={"Cache-Control": "no-store"}
    )


@app.get("/manager/", include_in_schema=False)
@app.get("/manager/{asset:path}", include_in_schema=False)
async def manager_files(asset: str = "", user: User = Depends(current_user)):
    require_not_resident(user)
    return FileResponse(
        resolve_static_file(MANAGER_DIR, asset), headers={"Cache-Control": "no-store"}
    )


@app.get("/admin/", include_in_schema=False)
@app.get("/admin/{asset:path}", include_in_schema=False)
async def admin_files(asset: str = "", user: User = Depends(current_user)):
    # The page itself is loadable by any non-tenant login (so the footer
    # link always works rather than 404ing for a landlord) - the actual
    # admin data behind it (/api/admin/info) stays admin-only, and the page
    # shows "Admins only." to anyone else. See api_admin_info below.
    require_not_resident(user)
    return FileResponse(
        resolve_static_file(ADMIN_DIR, asset), headers={"Cache-Control": "no-store"}
    )


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
    require_not_resident(user)
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
        # This user's own tenants, for the "send a notice" form - an admin
        # sees every tenant, a landlord only those under their own landlord_id.
        "tenants": [
            {"username": u.username, "display_name": u.display_name}
            for u in settings.users
            if u.role == ROLE_RESIDENT and (user.is_admin or u.landlord_id == user.landlord_id)
        ],
    }


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)


@app.post("/api/account/password")
async def api_change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(current_user),
) -> dict[str, str]:
    """Let a logged-in user change their own password.

    Re-checks the current password even though `current_user` already
    proved it correct for this request - defense in depth, and it means a
    stray autofilled/stale form can't silently change a password to
    something the user didn't intend.
    """
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    new_hash = hash_password(payload.new_password)
    changed = await accounts.set_password_hash(user.username, new_hash)
    if not changed:
        raise HTTPException(status_code=404, detail="Account not found.")

    # The new hash now needs to reach whatever Settings.load() actually
    # reads - the Postgres cache if that's the backend, and the @lru_cache
    # on get_settings() either way. See app/accounts.py's set_password_hash
    # docstring: it only writes the durable store, this is that refresh.
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        await preload_accounts_from_postgres(database_url)
    get_settings.cache_clear()
    return {"detail": "Password updated."}


@app.get("/api/admin/info")
async def api_admin_info(user: User = Depends(current_user)) -> dict[str, Any]:
    """Reference info for the admin page: who exists and which backend each
    piece of storage is using. Deliberately no secrets - not the DSN (a
    Postgres one embeds a password), not any API key, not password hashes.
    """
    if not user.is_admin:
        raise HTTPException(status_code=404, detail="No such page.")
    settings = get_settings()

    database_url = os.environ.get("DATABASE_URL", "").strip()
    supabase_url = settings.supabase_url

    return {
        "landlords": [
            {
                "id": landlord.id, "company": landlord.company,
                "signer_name": landlord.signer_name, "email": landlord.email,
            }
            for landlord in settings.landlords
        ],
        "users": [
            {
                "username": u.username, "display_name": u.display_name,
                "role": u.role, "landlord_id": u.landlord_id,
            }
            for u in settings.users
        ],
        "backends": {
            "records": "Supabase Postgres" if database_url else "local SQLite",
            "accounts": "Supabase Postgres" if database_url else "accounts.json",
            "files": (
                f"Supabase Storage ({settings.archive_dir.split(':', 1)[1]})"
                if settings.archive_dir.startswith("supabase:")
                else f"local disk ({settings.archive_dir})"
            ),
        },
        "links": {
            "github": "https://github.com/KevinKolb/LGD",
            "render": "https://dashboard.render.com",
            "supabase": (
                f"https://supabase.com/dashboard/project/"
                f"{supabase_url.removeprefix('https://').split('.')[0]}"
                if supabase_url else None
            ),
        },
    }


@app.get("/resident/", include_in_schema=False)
@app.get("/resident/{asset:path}", include_in_schema=False)
async def resident_files(asset: str = ""):
    """Public static files - no login. The page's own JS is what gates the
    notices section, by making an authenticated call to /api/notices."""
    return FileResponse(
        resolve_static_file(RESIDENT_DIR, asset), headers={"Cache-Control": "no-store"}
    )


@app.get("/applicant/", include_in_schema=False)
@app.get("/applicant/{asset:path}", include_in_schema=False)
async def applicant_files(asset: str = ""):
    """Public static files - no login, same as /resident/. The rental
    application form (POST /api/applications) lives here now, separate
    from /resident/'s logged-in notices - nobody has a resident login yet
    before they've applied."""
    return FileResponse(
        resolve_static_file(APPLICANT_DIR, asset), headers={"Cache-Control": "no-store"}
    )


@app.post("/api/applications", status_code=201)
async def api_submit_application(application: ApplicationRequest) -> dict[str, str]:
    """A prospective tenant's rental application. Public - no login, and
    deliberately so, since nobody has an account before they've applied."""
    settings = get_settings()
    await db.record_application(
        settings.db_path,
        applicant_name=application.applicant_name,
        applicant_email=application.applicant_email,
        applicant_phone=application.applicant_phone,
        consent_to_text=application.consent_to_text,
        property_interest=application.property_interest or None,
        desired_move_in=application.desired_move_in or None,
        message=application.message or None,
        roommates=[r.model_dump() for r in application.roommates],
    )
    return {"detail": "Application received."}


@app.get("/api/applications")
async def api_list_applications(user: User = Depends(current_user)) -> dict[str, Any]:
    """Admin-only: property_interest is free text the applicant typed, not
    a landlord id, so there's no way to scope an application to one
    landlord server-side. Admin reads it and routes manually."""
    if not user.is_admin:
        raise HTTPException(status_code=404, detail="No such page.")
    settings = get_settings()
    applications = await db.list_applications(settings.db_path)
    return {"applications": applications}


@app.post("/api/notices", status_code=201)
async def api_send_notice(
    notice: NoticeRequest,
    user: User = Depends(current_user),
) -> dict[str, str]:
    """A landlord/admin sends one tenant a free-form notice."""
    require_not_resident(user)
    settings = get_settings()
    tenant = settings.user_by_username(notice.tenant_username)
    if tenant is None or not tenant.is_resident:
        raise HTTPException(status_code=400, detail="Unknown tenant.")
    if not user.may_use_landlord(tenant.landlord_id):
        raise HTTPException(
            status_code=403, detail="That tenant is not one of yours."
        )
    await db.record_notice(
        settings.db_path,
        tenant_username=tenant.username,
        message=notice.message,
        created_by=user.username,
    )
    return {"detail": "Notice sent."}


@app.get("/api/notices")
async def api_list_notices(user: User = Depends(current_user)) -> dict[str, Any]:
    """A tenant's own notices, newest first."""
    if not user.is_resident:
        raise HTTPException(status_code=404, detail="No such page.")
    settings = get_settings()
    notices = await db.list_notices(settings.db_path, tenant_username=user.username)
    return {"notices": notices}


@app.post("/api/news", status_code=201)
async def api_post_news(
    news: NewsRequest,
    user: User = Depends(current_user),
) -> dict[str, str]:
    """A landlord/admin publishes a news post, from the manager dashboard."""
    require_not_resident(user)
    authorize_landlord(user, news.landlord_id)
    settings = get_settings()
    await db.record_news(
        settings.db_path,
        landlord_id=news.landlord_id,
        headline=news.headline,
        article=news.article,
        created_by=user.username,
    )
    return {"detail": "News posted."}


@app.get("/api/news")
async def api_list_news(user: User = Depends(current_user)) -> dict[str, Any]:
    """News for this user's own landlord, or every landlord's for an admin."""
    require_not_resident(user)
    settings = get_settings()
    landlord_id = None if user.is_admin else user.landlord_id
    news = await db.list_news(settings.db_path, landlord_id=landlord_id)
    return {"news": news}


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
