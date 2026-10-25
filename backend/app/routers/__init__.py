from fastapi import APIRouter

from ..channels import whatsapp
from . import chat, claim, files, health, ledger, resources, schemes, webhooks


def all_routers() -> list[APIRouter]:
    return [
        health.router,
        chat.router,
        schemes.router,
        claim.router,
        ledger.router,
        resources.router,
        webhooks.router,
        files.router,
        whatsapp.router,
    ]
