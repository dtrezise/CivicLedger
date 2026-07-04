from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routes import meta, search, people, trades, filings, market, events, sharecards

app = FastAPI(
    title="CivicLedger API",
    version="0.1.0",
    description="Congressional financial disclosure tracker",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(search.router)
app.include_router(people.router)
app.include_router(trades.router)
app.include_router(filings.router)
app.include_router(market.router)
app.include_router(events.router)
app.include_router(sharecards.router)


@app.get("/")
async def root():
    return {"name": "CivicLedger API", "version": "0.1.0"}
