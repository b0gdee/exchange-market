from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from routers import admin, balance, order, public, ws
import time

app = FastAPI(
    title="Exchange API FastAPI",
)


# Middleware for request processing
@app.middleware("http")
async def process_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    return response


# Exception handler
@app.exception_handler(Exception)
async def handle_exceptions(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"}
    )


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    return {
        "message": "Welcome Exchange Market",
        "SWAGGER": "/docs"
    }


# Include routers
app.include_router(public.router, prefix="/api/v1/public", tags=["public"])
app.include_router(order.router, prefix="/api/v1", tags=["order"])
app.include_router(balance.router, prefix="/api/v1", tags=["balance"])
app.include_router(admin.router, prefix="/api/v1", tags=["admin"])
app.include_router(ws.router, prefix="/ws", tags=["websocket"])


@app.on_event("startup")
async def startup():
    """Initialize Kafka"""
    from kafka.producer import init_producer
    from kafka.consumer import start_consumers

    await init_producer()
    await start_consumers()


@app.on_event("shutdown")
async def shutdown():
    """Shutdown Kafka"""
    from kafka.producer import close_producer
    await close_producer()