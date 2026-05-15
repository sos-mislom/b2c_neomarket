from __future__ import annotations

import hashlib
import html
from urllib.parse import quote

from fastapi import APIRouter, Response

from ..config import get_settings
from ..db import database_ready
from ..services import demo_metadata


router = APIRouter(tags=["system"])


def svg_palette(asset_path: str) -> tuple[str, str]:
    digest = hashlib.md5(asset_path.encode("utf-8"), usedforsecurity=False).hexdigest()
    start = f"#{digest[:6]}"
    end = f"#{digest[6:12]}"
    return start, end


def svg_dimensions(asset_path: str) -> tuple[int, int]:
    if "banner" in asset_path:
        return 1440, 640
    if "collection" in asset_path:
        return 1200, 720
    if "category" in asset_path:
        return 1200, 720
    return 960, 960


def svg_title(asset_path: str) -> str:
    filename = asset_path.split("/")[-1].split(".")[0].replace("-", " ").replace("_", " ").strip()
    return filename.title() or "NeoMarket"


@router.get("/readyz")
def readiness() -> dict:
    database_ready()
    return {"status": "ready"}


@router.get("/api/v1/bootstrap")
def bootstrap() -> dict:
    settings = get_settings()
    return {
        "app": {"name": settings.app_name, "env": settings.app_env, "version": "2.0.0"},
        "identity": demo_metadata(),
        "routes": {
            "home": "/",
            "catalog": "/catalog",
            "favorites": "/favorites",
            "cart": "/cart",
            "orders": "/orders",
        },
        "microfrontends": {
            "home": "/mf/home-mf.js",
            "catalog": "/mf/catalog-mf.js",
            "customer": "/mf/customer-mf.js",
        },
    }


@router.get("/cdn/{asset_path:path}")
def dynamic_cdn(asset_path: str) -> Response:
    width, height = svg_dimensions(asset_path)
    primary, secondary = svg_palette(asset_path)
    title = html.escape(svg_title(asset_path))
    safe_path = html.escape(asset_path)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="{width}" y2="{height}" gradientUnits="userSpaceOnUse">
      <stop stop-color="{primary}"/>
      <stop offset="1" stop-color="{secondary}"/>
    </linearGradient>
  </defs>
  <rect width="{width}" height="{height}" fill="url(#bg)"/>
  <circle cx="{width * 0.18:.0f}" cy="{height * 0.28:.0f}" r="{min(width, height) * 0.14:.0f}" fill="white" fill-opacity="0.10"/>
  <circle cx="{width * 0.78:.0f}" cy="{height * 0.74:.0f}" r="{min(width, height) * 0.18:.0f}" fill="white" fill-opacity="0.08"/>
  <rect x="{width * 0.07:.0f}" y="{height * 0.67:.0f}" width="{width * 0.50:.0f}" height="{height * 0.12:.0f}" rx="24" fill="white" fill-opacity="0.14"/>
  <text x="{width * 0.07:.0f}" y="{height * 0.28:.0f}" fill="white" font-family="Verdana, DejaVu Sans, sans-serif" font-size="{max(32, int(min(width, height) * 0.06))}" font-weight="700">{title}</text>
  <text x="{width * 0.07:.0f}" y="{height * 0.84:.0f}" fill="white" fill-opacity="0.72" font-family="Verdana, DejaVu Sans, sans-serif" font-size="{max(20, int(min(width, height) * 0.024))}">{safe_path}</text>
</svg>"""
    headers = {"Cache-Control": "public, max-age=3600"}
    return Response(content=svg, media_type="image/svg+xml", headers=headers)
