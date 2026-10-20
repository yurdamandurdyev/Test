from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit, unquote

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError

from .analytics import MAX_BYTES, InputError, analyze, export_csv
from .calls import score_calls

app = FastAPI(title="Sales Intelligence", docs_url=None, redoc_url=None, openapi_url=None)
SESSION_SECONDS = 8 * 3600
attempts: dict[str, list[float]] = defaultdict(list)


def configured() -> bool:
    return len(os.getenv("APP_PASSWORD", "")) >= 16 and len(os.getenv("SESSION_SECRET", "")) >= 32


def signature(payload: str) -> str:
    return hmac.new(os.environ["SESSION_SECRET"].encode(), payload.encode(), hashlib.sha256).hexdigest()


def authorized(request: Request) -> bool:
    if not configured(): return False
    value = request.cookies.get("si_session", "")
    try:
        timestamp, nonce, sig = value.split(".")
        age = time.time() - int(timestamp)
        return 0 <= age < SESSION_SECONDS and hmac.compare_digest(sig, signature(timestamp + "." + nonce))
    except (ValueError, KeyError):
        return False


def require_user(request: Request) -> None:
    if not authorized(request):
        raise HTTPException(401, "Войдите, чтобы работать с приватными данными.")


def mutation(request: Request) -> None:
    if request.headers.get("x-sales-client") != "web":
        raise HTTPException(403, "Запрос отклонён. Обновите страницу.")
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "Недопустимый источник запроса.")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > MAX_BYTES + 64_000:
                return JSONResponse({"detail": "Файл больше 2 МБ."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Некорректный размер запроса."}, status_code=400)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(InputError)
async def bad_input(request: Request, exc: InputError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "Некорректный запрос. Проверьте введённые данные."})


class Login(BaseModel):
    password: str = Field(max_length=256)


@app.get("/api/health")
def health():
    return {"status": "ok", "methodology_version": "1.0"}


@app.get("/api/session")
def session(request: Request):
    return {"authenticated": authorized(request), "configured": configured()}


@app.post("/api/login", dependencies=[Depends(mutation)])
async def login(request: Request, response: Response):
    if not configured():
        raise HTTPException(503, "Приватный режим ещё не настроен. Используйте демо.")
    payload_bytes = bytearray()
    async for chunk in request.stream():
        if len(payload_bytes) + len(chunk) > 4096:
            raise HTTPException(413, "Запрос входа слишком большой.")
        payload_bytes.extend(chunk)
    try:
        body = Login.model_validate_json(payload_bytes)
    except ValidationError:
        raise HTTPException(422, "Некорректный запрос. Проверьте введённые данные.")
    # Single-instance abuse mitigation; configure provider rate limits in production.
    key = request.client.host if request.client else "unknown"
    now = time.time()
    if len(attempts) > 2000: attempts.clear()
    attempts[key] = [t for t in attempts[key] if now - t < 300]
    if len(attempts[key]) >= 8:
        raise HTTPException(429, "Слишком много попыток. Попробуйте через пять минут.")
    attempts[key].append(now)
    if not hmac.compare_digest(body.password.encode(), os.environ["APP_PASSWORD"].encode()):
        raise HTTPException(401, "Пароль не подошёл.")
    payload = str(int(now)) + "." + secrets.token_hex(16)
    response.set_cookie("si_session", payload + "." + signature(payload), httponly=True, samesite="strict",
                        secure=os.getenv("COOKIE_SECURE", "true").lower() != "false", max_age=SESSION_SECONDS, path="/")
    return {"authenticated": True}


@app.post("/api/logout", dependencies=[Depends(mutation)])
def logout(response: Response):
    response.delete_cookie("si_session", path="/")
    return {"authenticated": False}


async def uploaded(request: Request) -> dict:
    name = unquote(request.headers.get("x-file-name", ""))
    if not name.lower().endswith(".csv"):
        raise InputError("Выберите файл с расширением .csv.")
    if request.headers.get("content-type", "").split(";")[0] not in ("text/csv", "application/csv", "application/vnd.ms-excel", "text/plain", "application/octet-stream"):
        raise InputError("Тип файла не поддерживается. Нужен текстовый CSV.")
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > MAX_BYTES:
            raise InputError("Файл больше 2 МБ.")
        payload.extend(chunk)
    return analyze(bytes(payload))


@app.post("/api/analyze", dependencies=[Depends(require_user), Depends(mutation)])
async def analyze_upload(request: Request):
    return await uploaded(request)


@app.post("/api/export", dependencies=[Depends(require_user), Depends(mutation)])
async def export_upload(request: Request):
    return Response(export_csv(await uploaded(request)), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="leads-normalized.csv"'})


@app.get("/api/calls", dependencies=[Depends(require_user)])
def calls():
    path = os.getenv("CALLS_ANNOTATIONS_PATH")
    inline = os.getenv("CALLS_ANNOTATIONS_JSON")
    if not path and not inline:
        return score_calls([])
    try:
        return score_calls(json.loads(Path(path).read_text(encoding="utf-8") if path else inline))
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Не удалось загрузить аннотации звонков. Проверьте настройку сервера.")


DEMO = """дата,имя,телефон,источник,бюджет
2026-10-19,Демо 01,DEMO-001,Сайт,5000000
2026-10-19,Демо 02,DEMO-002,Авито,0
2026-10-18,Демо 03,DEMO-003,Яндекс,9000000
2026-10-17,Демо 04,DEMO-004,Сайт,
2026-10-16,Демо 05,DEMO-005,Сарафан,7000000
"""


@app.get("/api/demo")
def demo():
    return {"demo": True, "report": analyze(DEMO.encode())}


@app.get("/api/demo.csv")
def demo_csv():
    return Response(DEMO, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="synthetic-demo.csv"'})
