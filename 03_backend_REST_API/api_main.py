"""
main.py
--------
REST API over the GenApp PostgreSQL database (migrated from IBM
GenApp's DB2/VSAM backends - see ../README.md and
../docs/MIGRATION_BLUEPRINT.md for the full migration story).

RUN:
    uvicorn main:app --reload

Then open http://localhost:8000/docs for interactive Swagger UI, or
http://localhost:8000/redoc for ReDoc.

Connection settings come from the standard PGHOST/PGPORT/PGDATABASE/
PGUSER/PGPASSWORD environment variables (see database.py), defaulting
to the same genapp/postgres/CHANGE_ME_LOCAL_ONLY values used throughout this
project.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_pool, close_pool
from routers import customers, customer_secure, policies, endowments, houses, motors, commercials, claims, meta


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    yield
    close_pool()


app = FastAPI(
    title="GenApp Insurance API",
    description=(
        "REST API over the PostgreSQL database migrated from IBM GenApp's "
        "DB2/VSAM backends. Covers customers, policies (endowment/house/"
        "motor/commercial detail), and claims, plus schema introspection "
        "and migration-validation endpoints under **meta**."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(customers.router)
app.include_router(customer_secure.router)
app.include_router(policies.router)
app.include_router(endowments.router)
app.include_router(houses.router)
app.include_router(motors.router)
app.include_router(commercials.router)
app.include_router(claims.router)
app.include_router(meta.router)


@app.get("/", tags=["meta"], summary="API root / health check")
def root():
    return {
        "service": "GenApp Insurance API",
        "status": "ok",
        "docs": "/docs",
        "tables": "/tables",
    }


@app.get("/health", tags=["meta"], summary="Liveness + database connectivity check")
def health():
    from database import get_conn
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"status": "ok", "database": "reachable"}
    except Exception as e:
        return {"status": "error", "database": "unreachable", "detail": str(e)}
