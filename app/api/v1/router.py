from fastapi import APIRouter

from app.api.v1 import admin, ai, auth, consumer, health, merchant, payments, wallet, web_forms

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(ai.router)
api_router.include_router(consumer.router)
api_router.include_router(merchant.router)
api_router.include_router(admin.router)
api_router.include_router(wallet.router)
api_router.include_router(web_forms.router)
api_router.include_router(payments.router)
