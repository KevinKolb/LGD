"""LGD web service.

Serves the static pages and the printable blank lease, plus a small JSON
API behind HTTP Basic for the manager and admin areas. Accounts and the
application and news records live in Supabase Postgres when configured,
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
    Manager,
    User,
    get_settings,
    preload_accounts_from_postgres,
)
from app.tenant_portal import ApplicationRequest, NewsRequest

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
PRINT_DIR = (Path(__file__).resolve().parent.parent / "documents" / "print").resolve()
RESIDENT_DIR = (Path(__file__).resolve().parent.parent / "resident").resolve()
APPLICANT_DIR = (Path(__file__).resolve().parent.parent / "applicant").resolve()
LOGIN_DIR = (Path(__file__).resolve().parent.parent / "login").resolve()
PROPERTIES_PATH = (Path(__file__).resolve().parent.parent / "documents" / "properties.json").resolve()
FAVICON_PATH = (Path(__file__).resolve().parent.parent / "favicon.ico").resolve()
ROOT_INDEX_PATH = (Path(__file__).resolve().parent.parent / "index.html").resolve()
# The blank, printable lease - generated from documents/lease.md by
# documents/print/generate_print_lease.py. Served here rather than added to
# MANAGER_DIR so there's still exactly one copy of it on disk.
BLANK_LEASE_PATH = (
    Path(__file__).resolve().parent.parent / "documents" / "print" / "lease_print.html"
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
        "LGD service ready (%d manager(s), %d user(s))",
        len(settings.managers),
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
    # Verify against a decoy hash when the user is unknown - or when they
    # exist but have no PBKDF2 hash at all, which is what a Supabase Auth
    # signup looks like here. Both take the same time and give the same
    # answer as a wrong password, rather than failing fast and saying so.
    expected_hash = user.password_hash if (user and user.password_hash) else DECOY_HASH
    ok = check_credentials(
        credentials.username,
        credentials.password,
        expected_username=credentials.username if user else "\0",
        expected_hash=expected_hash,
    )
    if not user or not ok:
        raise unauthorized
    return user


def require_dashboard_role(user: User) -> None:
    """Only managers and admins get the dashboard and its API.

    An allow-list, not "anyone who is not a resident": public signups on the
    website now create `applicant` logins (see app/config.py), and an
    exclusion list would have let every one of them in here the moment that
    role appeared.
    """
    if not user.may_use_dashboard:
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


def authorize_manager(user: User, manager_id: str) -> Manager:
    """Resolve a lessor id, refusing one this user may not act for."""
    settings = get_settings()
    manager = settings.manager_by_id(manager_id)
    if manager is None:
        raise HTTPException(status_code=400, detail="Unknown manager selected.")
    if not user.may_use_manager(manager_id):
        raise HTTPException(
            status_code=403,
            detail="You cannot act for that manager.",
        )
    return manager


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


@app.get("/documents/print/{asset:path}", include_in_schema=False)
async def print_files(asset: str, user: User = Depends(current_user)):
    """The blank paper lease, at the same relative path it has on GitHub
    Pages (../documents/print/lease_print.html from the manager page), so one href
    works on both hosts. /api/blank-lease still serves the same file."""
    require_dashboard_role(user)
    path = resolve_static_file(PRINT_DIR, asset)
    # The documents are HTML; Send's PDF maker (vendor/) is a script.
    return FileResponse(
        path,
        media_type="text/html" if path.suffix == ".html" else None,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/documents/properties.json", include_in_schema=False)
async def properties_file(user: User = Depends(current_user)):
    """The table of apartments, at the same relative path it has on GitHub
    Pages, for the manager page's applicant form and the rent register."""
    require_dashboard_role(user)
    return FileResponse(PROPERTIES_PATH, media_type="application/json",
                        headers={"Cache-Control": "no-store"})


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
    require_dashboard_role(user)
    return FileResponse(
        resolve_static_file(MANAGER_DIR, asset), headers={"Cache-Control": "no-store"}
    )


@app.get("/admin/", include_in_schema=False)
@app.get("/admin/{asset:path}", include_in_schema=False)
async def admin_files(asset: str = "", user: User = Depends(current_user)):
    # The page itself is loadable by any non-tenant login (so the footer
    # link always works rather than 404ing for a manager) - the actual
    # admin data behind it (/api/admin/info) stays admin-only, and the page
    # shows "Admins only." to anyone else. See api_admin_info below.
    require_dashboard_role(user)
    return FileResponse(
        resolve_static_file(ADMIN_DIR, asset), headers={"Cache-Control": "no-store"}
    )


@app.get("/api/blank-lease", include_in_schema=False)
async def api_blank_lease(user: User = Depends(current_user)):
    """The blank, unsigned lease for printing or downloading.

    Managers and admins only, the same as the /documents/print/ route that
    serves this very file - it had been left open to any logged-in account,
    which quietly meant residents too.

    One route serves both dashboard buttons: opening it in a new tab is the
    "Print" button (the page has its own print CSS and an on-page Print
    button), and the "Download" button hits the same URL with an anchor
    `download` attribute, which makes the browser save it instead of
    navigating - no server-side distinction needed.
    """
    require_dashboard_role(user)
    if not BLANK_LEASE_PATH.is_file():
        raise HTTPException(
            status_code=404,
            detail="Blank lease not generated yet - run "
            "documents/print/generate_print_lease.py.",
        )
    return FileResponse(
        BLANK_LEASE_PATH, media_type="text/html", headers={"Cache-Control": "no-store"}
    )


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@app.get("/api/config")
async def api_config(user: User = Depends(current_user)) -> dict[str, Any]:
    require_dashboard_role(user)
    settings = get_settings()
    return {
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "roles": sorted(user.roles),
            "is_admin": user.is_admin,
        },
        # Only the managers this user may act for. Emails stay server-side.
        "managers": [
            {"id": manager.id, "name": manager.name}
            for manager in settings.managers_for(user)
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
        "managers": [
            {
                "id": manager.id, "name": manager.name,
                "signer_name": manager.signer_name, "email": manager.email,
            }
            for manager in settings.managers
        ],
        "users": [
            {
                "username": u.username, "display_name": u.display_name,
                "role": u.role_label, "roles": sorted(u.roles),
                "manager_id": u.manager_id,
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
    """Public static files - no login, and nothing on the page needs one
    now that notices are gone: it is contact details and manager name."""
    return FileResponse(
        resolve_static_file(RESIDENT_DIR, asset), headers={"Cache-Control": "no-store"}
    )


@app.get("/applicant/", include_in_schema=False)
@app.get("/applicant/{asset:path}", include_in_schema=False)
async def applicant_files(asset: str = ""):
    """Public static files - no login, same as /resident/. The rental
    application form (POST /api/applications) lives here now, separate from
    /resident/ - nobody has a resident login before they have applied."""
    return FileResponse(
        resolve_static_file(APPLICANT_DIR, asset), headers={"Cache-Control": "no-store"}
    )


@app.get("/login/", include_in_schema=False)
@app.get("/login/{asset:path}", include_in_schema=False)
async def login_files(asset: str = ""):
    """The sign-in page. Public by necessity - a login form behind a login
    is no login form. It talks to Supabase Auth from the browser and never
    to this app, so it works identically here and on GitHub Pages."""
    return FileResponse(
        resolve_static_file(LOGIN_DIR, asset), headers={"Cache-Control": "no-store"}
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
    a manager id, so there's no way to scope an application to one
    manager server-side. Admin reads it and routes manually."""
    if not user.is_admin:
        raise HTTPException(status_code=404, detail="No such page.")
    settings = get_settings()
    applications = await db.list_applications(settings.db_path)
    return {"applications": applications}


@app.post("/api/news", status_code=201)
async def api_post_news(
    news: NewsRequest,
    user: User = Depends(current_user),
) -> dict[str, str]:
    """A manager/admin publishes a news post, from the manager dashboard."""
    require_dashboard_role(user)
    authorize_manager(user, news.manager_id)
    settings = get_settings()
    await db.record_news(
        settings.db_path,
        manager_id=news.manager_id,
        headline=news.headline,
        article=news.article,
        created_by=user.username,
    )
    return {"detail": "News posted."}


@app.get("/api/news")
async def api_list_news(user: User = Depends(current_user)) -> dict[str, Any]:
    """News for this user's own manager, or every manager's for an admin."""
    require_dashboard_role(user)
    settings = get_settings()
    manager_id = None if user.is_admin else user.manager_id
    news = await db.list_news(settings.db_path, manager_id=manager_id)
    return {"news": news}


class ApplicantRequest(BaseModel):
    email: str = Field(max_length=254)
    address: str = Field(default="", max_length=200)
    unit: str = Field(default="", max_length=20)


@app.post("/api/applicants", status_code=201)
async def api_add_applicant(
    applicant: ApplicantRequest,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """A manager/admin adds an applicant from the manager page. Always the
    caller's own company - never a company the request names. The website
    does the same through Supabase (migration 002's create_applicant)."""
    require_dashboard_role(user)
    settings = get_settings()
    try:
        created = await db.create_applicant(
            settings.db_path,
            email=applicant.email,
            address=applicant.address,
            unit=applicant.unit,
            manager_id=user.manager_id,
            is_admin=user.is_admin,
        )
    except db.ApplicantError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return {"applicant": {**created, "has_login": False}}


@app.get("/api/applicants")
async def api_list_applicants(archived: bool = False,
                              user: User = Depends(current_user)) -> dict[str, Any]:
    """This company's applicants, or every company's for an admin, newest
    first - the current ones, or with ?archived=true the archived ones -
    each saying whether they have a login yet."""
    require_dashboard_role(user)
    settings = get_settings()
    manager_id = None if user.is_admin else user.manager_id
    applicants = await db.list_applicants(settings.db_path, manager_id=manager_id,
                                          archived=archived)
    with_login = {u.person_id for u in settings.users if u.person_id}
    for applicant in applicants:
        applicant["has_login"] = applicant["id"] in with_login
    return {"applicants": applicants}


@app.get("/api/residents")
async def api_list_residents(month: str | None = None,
                             user: User = Depends(current_user)) -> dict[str, Any]:
    """Residents and their units, for the manager page's rent register -
    this company's, or every company's for an admin. With ?month=YYYY-MM,
    only residents whose recorded lease covers that month."""
    require_dashboard_role(user)
    settings = get_settings()
    manager_id = None if user.is_admin else user.manager_id
    try:
        residents = await db.list_residents(settings.db_path, manager_id=manager_id, month=month)
    except db.RentRegisterError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return {"residents": residents}


class ResidentRequest(BaseModel):
    address: str = Field(max_length=200)
    unit: str = Field(default="", max_length=20)
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=40)
    lease_start: str = Field(default="", max_length=10)
    lease_end: str = Field(default="", max_length=10)
    person_id: str | None = Field(default=None, max_length=64)


@app.post("/api/residents")
async def api_save_resident(payload: ResidentRequest,
                            user: User = Depends(current_user)) -> dict[str, Any]:
    """Resident Entry: add a resident (only the apartment is needed), or
    with person_id change one."""
    require_dashboard_role(user)
    try:
        resident = await db.save_resident(get_settings().db_path, manager_id=user.manager_id,
                                          is_admin=user.is_admin, **payload.model_dump())
    except db.ResidentError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return {"resident": resident}


@app.delete("/api/residents/{person_id}")
async def api_remove_resident(person_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    """Take a resident out of their apartment; they stay in the directory."""
    require_dashboard_role(user)
    try:
        resident = await db.remove_resident(get_settings().db_path, manager_id=user.manager_id,
                                            is_admin=user.is_admin, person_id=person_id)
    except db.ResidentError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return {"resident": resident}


class RentPaymentRequest(BaseModel):
    month: str = Field(max_length=7)
    address: str = Field(max_length=200)
    unit: str = Field(default="", max_length=20)
    received_on: str = Field(default="", max_length=10)


@app.get("/api/rent-payments")
async def api_list_rent_payments(month: str, user: User = Depends(current_user)) -> dict[str, Any]:
    """The dates this company's rent was received in a month."""
    require_dashboard_role(user)
    try:
        payments = await db.list_rent_payments(get_settings().db_path, manager_id=user.manager_id, month=month)
    except db.RentRegisterError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return {"payments": payments}


@app.put("/api/rent-payments")
async def api_set_rent_payment(payload: RentPaymentRequest,
                               user: User = Depends(current_user)) -> dict[str, Any]:
    """Record (or, with no date, take back) the date an apartment's rent
    for a month was received."""
    require_dashboard_role(user)
    try:
        payment = await db.set_rent_payment(
            get_settings().db_path, manager_id=user.manager_id, month=payload.month,
            address=payload.address, unit=payload.unit, received_on=payload.received_on,
            person_id=user.person_id)
    except db.RentRegisterError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return {"payment": payment}


class SiteColorsRequest(BaseModel):
    accent: str = Field(default="", max_length=7)
    accent2: str = Field(default="", max_length=7)


@app.get("/api/site-colors")
async def api_site_colors() -> dict[str, Any]:
    """Public, like every page that shows them: the two main colors an admin
    chose (shared/theme.js reads this before trying Supabase)."""
    return await db.get_site_colors(get_settings().db_path)


@app.put("/api/site-colors")
async def api_set_site_colors(payload: SiteColorsRequest,
                              user: User = Depends(current_user)) -> dict[str, Any]:
    """Admins only; both empty goes back to each page's own colors."""
    if not user.is_admin:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return await db.set_site_colors(get_settings().db_path, accent=payload.accent,
                                        accent2=payload.accent2, person_id=user.person_id)
    except db.SiteColorsError as error:
        raise HTTPException(status_code=422, detail=str(error))


class OpenApartment(BaseModel):
    address: str = Field(max_length=200)
    unit: str = Field(default="", max_length=20)


class OpenApartmentsRequest(BaseModel):
    apartments: list[OpenApartment] = Field(max_length=500)


@app.get("/api/open-apartments")
async def api_list_open_apartments(user: User = Depends(current_user)) -> dict[str, Any]:
    """The apartments this company is accepting applications for - the
    manager page's Accept Applications popup. The website does the same
    through Supabase (migration 004's list_open_apartments)."""
    require_dashboard_role(user)
    settings = get_settings()
    return {"apartments": await db.list_open_apartments(settings.db_path, manager_id=user.manager_id)}


@app.get("/api/accepting-applications")
async def api_accepting_applications() -> dict[str, bool]:
    """Public: whether any property is accepting applications - yes or no,
    nothing more. The applicant page shows Apply only while it is."""
    return {"accepting": await db.accepting_applications(get_settings().db_path)}


@app.put("/api/open-apartments")
async def api_set_open_apartments(payload: OpenApartmentsRequest,
                                  user: User = Depends(current_user)) -> dict[str, Any]:
    """Replace the list - always the caller's own company, never one the
    request names."""
    require_dashboard_role(user)
    settings = get_settings()
    try:
        apartments = await db.set_open_apartments(
            settings.db_path, manager_id=user.manager_id,
            apartments=[item.model_dump() for item in payload.apartments])
    except db.OpenApartmentsError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return {"apartments": apartments}


class ArchiveRequest(BaseModel):
    archived: bool


@app.post("/api/applicants/{person_id}/archive")
async def api_archive_applicant(person_id: str, payload: ArchiveRequest,
                                user: User = Depends(current_user)) -> dict[str, Any]:
    """Archive an applicant - off the list, kept in the directory - or bring
    one back. Only within the caller's own company, unless an admin."""
    require_dashboard_role(user)
    settings = get_settings()
    try:
        applicant = await db.set_applicant_archived(
            settings.db_path, person_id=person_id, archived=payload.archived,
            manager_id=None if user.is_admin else user.manager_id)
    except db.ApplicantError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return {"applicant": applicant}


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
