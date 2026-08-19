import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pymysql
import redis
from fastapi import FastAPI, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pymysql.cursors import DictCursor
from redis.exceptions import RedisError


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "mysql"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "database": required_environment("DB_NAME"),
    "user": required_environment("DB_USER"),
    "password": required_environment("DB_PASSWORD"),
    "cursorclass": DictCursor,
    "connect_timeout": 3,
}

REDIS_CLIENT = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=required_environment("REDIS_PASSWORD"),
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "30"))
CACHE_KEY = "visits:total"

HTTP_REQUESTS = Counter(
    "backend_http_requests_total",
    "Total de requisições HTTP recebidas pelo backend.",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "backend_http_request_duration_seconds",
    "Duração das requisições HTTP do backend.",
    ["method", "path"],
)
CACHE_REQUESTS = Counter(
    "backend_cache_requests_total",
    "Resultado das consultas ao cache Redis.",
    ["result"],
)
DATABASE_ERRORS = Counter(
    "backend_database_errors_total",
    "Total de erros de acesso ao MySQL.",
    ["operation"],
)


def configure_logging() -> logging.Logger:
    app_logger = logging.getLogger("backend")
    app_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s level=%(levelname)s message=%(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    app_logger.addHandler(stream_handler)

    log_file = Path(os.getenv("LOG_FILE", "/app/logs/backend.log"))
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
        )
        file_handler.setFormatter(formatter)
        app_logger.addHandler(file_handler)
    except OSError as error:
        app_logger.warning("log_em_arquivo_indisponivel erro=%s", error)

    return app_logger


logger = configure_logging()


def open_database():
    return pymysql.connect(**DB_CONFIG)


async def prepare_database() -> None:
    for attempt in range(1, 31):
        try:
            connection = open_database()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS visits (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                connection.commit()
                logger.info("banco_pronto")
                return
            finally:
                connection.close()
        except pymysql.MySQLError as error:
            logger.warning(
                "aguardando_banco tentativa=%s erro=%s",
                attempt,
                error.__class__.__name__,
            )
            await asyncio.sleep(2)
    raise RuntimeError("MySQL não ficou disponível após 30 tentativas")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await prepare_database()
    yield


app = FastAPI(
    title="Projeto Final Docker",
    version="2.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.middleware("http")
async def collect_http_metrics(request: Request, call_next):
    started_at = time.perf_counter()
    response_status = 500
    try:
        response = await call_next(request)
        response_status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        HTTP_REQUESTS.labels(
            method=request.method,
            path=route_path,
            status=str(response_status),
        ).inc()
        HTTP_DURATION.labels(
            method=request.method,
            path=route_path,
        ).observe(time.perf_counter() - started_at)


def cached_visit_total() -> int | None:
    try:
        cached_value = REDIS_CLIENT.get(CACHE_KEY)
        if cached_value is None:
            CACHE_REQUESTS.labels(result="miss").inc()
            return None
        CACHE_REQUESTS.labels(result="hit").inc()
        return int(cached_value)
    except (RedisError, ValueError) as error:
        CACHE_REQUESTS.labels(result="error").inc()
        logger.warning("cache_indisponivel erro=%s", error.__class__.__name__)
        return None


def update_visit_cache(total: int) -> None:
    try:
        REDIS_CLIENT.setex(CACHE_KEY, CACHE_TTL_SECONDS, total)
    except RedisError as error:
        logger.warning("cache_nao_atualizado erro=%s", error.__class__.__name__)


def invalidate_visit_cache() -> None:
    try:
        REDIS_CLIENT.delete(CACHE_KEY)
    except RedisError as error:
        logger.warning("cache_nao_invalidado erro=%s", error.__class__.__name__)


@app.get("/health", tags=["operação"])
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "backend"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(
        content=generate_latest(),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )


@app.get("/ready", tags=["operação"])
def readiness() -> dict[str, str]:
    try:
        connection = open_database()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        finally:
            connection.close()
    except pymysql.MySQLError as error:
        DATABASE_ERRORS.labels(operation="readiness").inc()
        logger.error("banco_indisponivel erro=%s", error.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL indisponível",
        ) from error
    redis_status = "ready"
    try:
        REDIS_CLIENT.ping()
    except RedisError as error:
        redis_status = "degraded"
        logger.warning("redis_indisponivel erro=%s", error.__class__.__name__)

    return {"status": "ready", "mysql": "ready", "redis": redis_status}


@app.get("/api/visits", tags=["visitas"])
def count_visits() -> dict[str, int]:
    cached_total = cached_visit_total()
    if cached_total is not None:
        return {"total": cached_total}

    try:
        connection = open_database()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM visits")
                row = cursor.fetchone()
        finally:
            connection.close()
    except pymysql.MySQLError as error:
        DATABASE_ERRORS.labels(operation="read").inc()
        logger.error("consulta_falhou erro=%s", error.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL indisponível",
        ) from error

    total = int(row["total"])
    update_visit_cache(total)
    return {"total": total}


@app.post("/api/visits", status_code=status.HTTP_201_CREATED, tags=["visitas"])
def register_visit() -> dict[str, int]:
    connection = None
    try:
        connection = open_database()
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO visits () VALUES ()")
            visit_id = cursor.lastrowid
        connection.commit()
        invalidate_visit_cache()
        logger.info("visita_registrada id=%s", visit_id)
        return {"id": int(visit_id)}
    except pymysql.MySQLError as error:
        DATABASE_ERRORS.labels(operation="write").inc()
        if connection is not None:
            connection.rollback()
        logger.error("gravacao_falhou erro=%s", error.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL indisponível",
        ) from error
    finally:
        if connection is not None:
            connection.close()
