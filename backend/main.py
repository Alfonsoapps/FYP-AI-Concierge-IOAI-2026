from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.admin import router as admin_router
from api.v1.chat import router as chat_router

app = FastAPI(title="IOAI 2027 AI Concierge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
