from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import check_connection, close_driver
from .routes.courses import router as courses_router
from .routes.courses import universities_router, search_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_driver()


app = FastAPI(title="Cours Interuniversitaire API", lifespan=lifespan)

app.include_router(courses_router)
app.include_router(universities_router)
app.include_router(search_router)


@app.get("/health")
def health():
    db_ok = check_connection()
    return {"status": "ok" if db_ok else "degraded", "neo4j": db_ok}
