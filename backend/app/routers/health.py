from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import __version__
from ..config import Settings
from ..deps import settings_dep
from ..models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(settings_dep)) -> HealthResponse:
    return HealthResponse(
        version=__version__,
        tinyfish_mode=settings.tinyfish_mode,
        db_backend=settings.db_backend,
        demo_state=settings.demo_state,
        demo_district=settings.demo_district,
        tinyfish_configured=settings.tinyfish_mode == "live" and bool(settings.tinyfish_api_key),
        whatsapp_configured=bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_whatsapp_from),
        speech_to_text_configured=bool(settings.bhashini_user_id and settings.bhashini_api_key),
        public_webhook_ready=settings.public_base_url.startswith("https://") and bool(settings.tinyfish_webhook_token),
        watch_mode_ready=(
            settings.tinyfish_mode == "live"
            and bool(settings.tinyfish_api_key)
            and settings.public_base_url.startswith("https://")
            and bool(settings.tinyfish_webhook_token)
        ),
    )
