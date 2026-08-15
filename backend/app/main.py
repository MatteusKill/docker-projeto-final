import asyncio
import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pymysql
from fastapi import FastAPI, HTTPException, status
from pymysql.cursors import DictCursor


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
    title="Projeto Final Básico",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.get("/health", tags=["operação"])
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "backend"}


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
        logger.error("banco_indisponivel erro=%s", error.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL indisponível",
        ) from error
    return {"status": "ready", "mysql": "ready"}


@app.get("/api/visits", tags=["visitas"])
def count_visits() -> dict[str, int]:
    try:
        connection = open_database()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM visits")
                row = cursor.fetchone()
        finally:
            connection.close()
    except pymysql.MySQLError as error:
        logger.error("consulta_falhou erro=%s", error.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL indisponível",
        ) from error

    return {"total": int(row["total"])}


@app.post("/api/visits", status_code=status.HTTP_201_CREATED, tags=["visitas"])
def register_visit() -> dict[str, int]:
    connection = None
    try:
        connection = open_database()
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO visits () VALUES ()")
            visit_id = cursor.lastrowid
        connection.commit()
        logger.info("visita_registrada id=%s", visit_id)
        return {"id": int(visit_id)}
    except pymysql.MySQLError as error:
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
