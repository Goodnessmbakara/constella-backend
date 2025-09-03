#from tester import migrate_all_tenants_to_milvus
import json
import requests
from utils.notifs import initialize_firebase, send_ios_image_notification, send_notification
import logging
# from utils.constella.retry_queue import process_retry_queue
import sentry_sdk
from constants import is_dev, is_scheduler
from utils.encryption import decrypt_request
import jwt
from db.weaviate.weaviate_client import client
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler
from user_agents import parse
import atexit
import signal
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# from db.milvus.milvus_client import client as milvus_client


if not is_scheduler:
    from db.weaviate.weaviate_client import client

# Import routers
if not is_scheduler:
    from routers.constella import router as constellaRouter
    from routers.payments import router as paymentsRouter
    from routers.revenuecat import router as revenuecatRouter
    from routers.constella_app import router as constellaAppRouter
    from routers.stella import router as stellaRouter
    from routers.auth import router as authRouter
    from routers.web_app import router as webAppRouter
    from routers.notifications import router as notificationsRouter
    from routers.misc.admin import router as adminRouter
    from routers.misc.helpers import router as helpersRouter

    # External API routers
    from routers.constella_external_api import router as constellaExternalApiRouter

    # Constella DB routers
    from routers.constella_db.notes import router as constellaDBNoteRouter
    from routers.constella_db.tags import router as constellaDBTagRouter
    # from routers.constella_db.tag_websocket import router as constellaDBTagWebSocketRouter
    from routers.constella_db.daily_notes import router as constellaDBDailyNoteRouter
    from routers.constella_db.misc import router as constellaDBMiscRouter
    from routers.constella_db.general import router as constellaDBGeneralRouter
    from routers.constella_db.note_bodies import router as constellaDBNoteBodyRouter
    from routers.integrations import router as integrationsRouter
    from utils.constella.retry_queue import process_retry_queue

    # Horizon routers
    from routers.horizon.assist import router as horizonAssistRouter
    from routers.horizon.context import router as horizonContextRouter
    from routers.horizon.create import router as horizonCreateRouter
    from routers.horizon.orb import router as horizonOrbRouter
    from routers.horizon.audio import router as horizonAudioRouter
    from routers.horizon.db import router as horizonDBRouter
    from routers.horizon.meetings import router as horizonMeetingsRouter
    from routers.horizon.integrations import router as horizonIntegrationsRouter
    from routers.horizon.autoloop import router as horizonAutoloopRouter
    from routers.horizon.auth import router as horizonAuthRouter

    # Aury routers
    from routers.aury.analysis import router as auryAnalysisRouter
    from routers.aury.general import router as auryGeneralRouter


if is_scheduler:
    from utils.constella.scheduled.s3_jobs import cleanup_old_deleted_records
    from utils.constella.scheduled.payment_jobs import distribute_monthly_credits


if not is_scheduler and not is_dev:
    sentry_sdk.init(
        dsn="https://4bdf2b546f30093d4768949762ad024e@o4508400776052736.ingest.us.sentry.io/4508598702374912",
        # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for tracing.
            traces_sample_rate=0.7,
            _experiments={
                # Set continuous_profiling_auto_start to True
                # to automatically start the profiler on when
                # possible.
                "continuous_profiling_auto_start": True,
            },
        debug=False
    )


app = FastAPI()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    exc_str = f'{exc}'.replace('\n', ' ').replace('   ', ' ')
    logging.error(f"{request}: {exc_str}")
    print("ERROR: ", exc_str)
    content = {'status_code': 10422, 'message': exc_str, 'data': None}
    return JSONResponse(content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    # Adjust this to the specific origins you want to allow
    allow_origins=["*"],
    allow_credentials=True,
    # Adjust this to the specific methods you want to allow
    allow_methods=["*"],
    # Adjust this to the specific headers you want to allow
    allow_headers=["*"],
)

secret_key = os.getenv("JWT_SECRET")


# Middleware before route
@app.middleware("http")
async def mobile_tracker_middleware(request: Request, call_next):
    user_agent_string = request.headers.get("user-agent")
    device_id = request.headers.get("device-id")
    access_token = request.headers.get("access-token")
    if access_token:
        try:
            access_data = jwt.decode(
                access_token.encode(), secret_key, algorithms=["HS256"])
        except Exception as e:
            print("Error decoding access token: ", e)
            access_data = None
    else:
        access_data = None

    user_agent = parse(user_agent_string)

    # pass device type
    device_type = "mobile" if user_agent.is_mobile else "pc" if "Dart" not in user_agent_string else "mobile"

    # Add device_type, device_id, and variables to request state
    request.state.device_type = device_type
    request.state.device_id = device_id
    request.state.access_data = access_data
    response = await call_next(request)
    return response


@app.middleware("http")
async def decrypt_request_middleware(request: Request, call_next):
    return await decrypt_request(request, call_next)


# Add routers to app
if not is_scheduler:
    app.include_router(constellaRouter)
    app.include_router(paymentsRouter)
    app.include_router(revenuecatRouter)
    app.include_router(constellaAppRouter)
    app.include_router(integrationsRouter)
    app.include_router(constellaExternalApiRouter)
    app.include_router(authRouter)
    app.include_router(stellaRouter)
    app.include_router(webAppRouter)
    app.include_router(notificationsRouter)
    app.include_router(adminRouter)
    app.include_router(helpersRouter)

    # Constella DB routers
    app.include_router(constellaDBNoteRouter)
    app.include_router(constellaDBTagRouter)
    # app.include_router(constellaDBTagWebSocketRouter)
    app.include_router(constellaDBDailyNoteRouter)
    app.include_router(constellaDBMiscRouter)
    app.include_router(constellaDBGeneralRouter)
    app.include_router(constellaDBNoteBodyRouter)

    # Horizon routers
    app.include_router(horizonAssistRouter)
    app.include_router(horizonContextRouter)
    app.include_router(horizonCreateRouter)
    app.include_router(horizonOrbRouter)
    app.include_router(horizonAudioRouter)
    app.include_router(horizonDBRouter)
    app.include_router(horizonMeetingsRouter)
    app.include_router(horizonIntegrationsRouter)
    app.include_router(horizonAutoloopRouter)
    app.include_router(horizonAuthRouter)

    # Aury routers
    app.include_router(auryAnalysisRouter)
    app.include_router(auryGeneralRouter)

# On staging, run the retry queue every 10 minutes
# NOTE: can make it more robust by running on a single thread process as this will be run across all workers


@app.on_event('startup')
async def init_data():
    if os.getenv("ENV") == "staging":
        print('starting scheduler')
        scheduler = BackgroundScheduler()
        scheduler.remove_all_jobs()
        from utils.constella.retry_queue import process_retry_queue
        scheduler.add_job(process_retry_queue, 'cron', minute='*/3')
        scheduler.start()

    # Initialize Firebase and run delete accounts
    initialize_firebase("admin_sdk.json")

    # migrate_all_tenants_to_milvus()

    # Delete accounts' data
    # import routers.misc.admin as admin_router
    # await admin_router.delete_accounts()

# Root route


@app.get("/")
async def root():
    return {"message": "Tutils <3"}


@app.on_event("shutdown")
async def shutdown_event():
    try:
        if not is_scheduler:
            client.close()
    except Exception as e:
        print(f"Error during graceful shutdown: {e}")

# Handle unexpected shutdowns gracefully


def handle_unexpected_shutdown(signum, frame):
    print("Unexpected shutdown detected. Attempting to close client...")
    try:
        if not is_scheduler:
            client.close()
    except Exception as e:
        print(f"Error closing client during unexpected shutdown: {e}")
    finally:
        print("Shutdown complete.")


# Register the handler for common signals
signal.signal(signal.SIGTERM, handle_unexpected_shutdown)
signal.signal(signal.SIGINT, handle_unexpected_shutdown)

# Use atexit to handle other unexpected exits
atexit.register(lambda: handle_unexpected_shutdown(None, None))

# Initialize the scheduler
if is_scheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(cleanup_old_deleted_records, 'interval', hours=1)
    scheduler.add_job(distribute_monthly_credits,
                      'interval', minutes=2)  # Run every 2
    scheduler.start()


# Everything from the RPC / PubSub stack                               ↓↓↓
NOISY_LOGGERS = [
    "fastapi.ws_rpc",          # fastapi-websocket-rpc + pubsub wrapper
    "broadcaster",             # redis / kafka / postgres backend driver
    "aioredis",                # the Redis client used by broadcaster
]

for name in NOISY_LOGGERS:
    logging.getLogger(name).setLevel(logging.ERROR)
