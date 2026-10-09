import math
import threading
import time
import uuid
from collections import deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

EMAIL = "24ds3000094@ds.study.iitm.ac.in"
ALLOWED_ORIGINS = [
    "https://app-os8vhs.example.com",
    "https://exam.sanand.workers.dev",
]
RATE = 14
WINDOW = 10.0

app = FastAPI()
lock = threading.Lock()
hits: dict[str, deque] = {}


# Innermost: rate limiter
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    client_id = request.headers.get("x-client-id")
    if client_id and request.method != "OPTIONS":
        now = time.monotonic()
        with lock:
            dq = hits.setdefault(client_id, deque())
            while dq and now - dq[0] >= WINDOW:
                dq.popleft()
            if len(dq) >= RATE:
                retry = max(1, math.ceil(WINDOW - (now - dq[0])))
                return JSONResponse(
                    {"detail": "rate limit exceeded"},
                    status_code=429,
                    headers={"Retry-After": str(retry)},
                )
            dq.append(now)
    return await call_next(request)


# Middle: request context (wraps the limiter, so 429s carry the ID too)
@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


# Outermost: CORS (added last, so even 429 responses get CORS headers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id", "Content-Type"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


@app.get("/ping")
def ping(request: Request):
    return {"email": EMAIL, "request_id": request.state.request_id}