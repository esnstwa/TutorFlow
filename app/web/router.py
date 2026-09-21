from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.web.navigation import get_auth_navigation
from app.web.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse, name="landing")
async def landing(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="pages/landing.html",
        context={"navigation": get_auth_navigation(request)},
    )


@router.get("/login", response_class=HTMLResponse, name="auth_login")
async def login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="pages/login.html",
        context={"navigation": get_auth_navigation(request)},
    )
