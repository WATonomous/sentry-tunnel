import json
import os
import time
import urllib

import flask
from flask_cors import CORS
from flask import request
import logging
import requests
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.crons import monitor


ALLOWED_SENTRY_HOSTS = set([s.strip() for s in os.environ.get("ALLOWED_SENTRY_HOSTS", "").split(",") if s.strip()])
ALLOWED_SENTRY_PROJECT_IDS = set([s.strip() for s in os.environ.get("ALLOWED_SENTRY_PROJECT_IDS", "").split(",") if s.strip()])
ALLOWED_SENTRY_DSNS = set([s.strip() for s in os.environ.get("ALLOWED_SENTRY_DSNS", "").split(",") if s.strip()])
LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG")
PORT = os.environ.get("PORT", 5000)
HOST = os.environ.get("HOST", "0.0.0.0")

logging.basicConfig(level=LOG_LEVEL)

# BUILD_INFO is generated by the build pipeline (e.g. docker/metadata-action).
# It looks like:
# {"tags":["ghcr.io/watonomous/repo-ingestion:main"],"labels":{"org.opencontainers.image.title":"repo-ingestion","org.opencontainers.image.description":"Simple server to receive file changes and open GitHub pull requests","org.opencontainers.image.url":"https://github.com/WATonomous/repo-ingestion","org.opencontainers.image.source":"https://github.com/WATonomous/repo-ingestion","org.opencontainers.image.version":"main","org.opencontainers.image.created":"2024-01-20T16:10:39.421Z","org.opencontainers.image.revision":"1d55b62b15c78251e0560af9e97927591e260a98","org.opencontainers.image.licenses":""}}
BUILD_INFO=json.loads(os.getenv("DOCKER_METADATA_OUTPUT_JSON", "{}"))
IS_SENTRY_ENABLED = os.getenv("SENTRY_DSN") is not None

# Set up Sentry
if IS_SENTRY_ENABLED:
    build_labels = BUILD_INFO.get("labels", {})
    image_title = build_labels.get("org.opencontainers.image.title", "unknown_image")
    image_version = build_labels.get("org.opencontainers.image.version", "unknown_version")
    image_rev = build_labels.get("org.opencontainers.image.revision", "unknown_rev")

    sentry_config = {
        "dsn": os.environ["SENTRY_DSN"],
        "environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "unknown"),
        "release": os.getenv("SENTRY_RELEASE", f'{image_title}:{image_version}@{image_rev}'),
    }

    logging.info(f"Sentry SDK version: {sentry_sdk.VERSION}")
    logging.info(f"Sentry DSN found. Setting up Sentry with config: {sentry_config}")

    sentry_logging = LoggingIntegration(
        level=logging.INFO,        # Capture info and above as breadcrumbs
        event_level=logging.ERROR  # Send errors as events
    )

    def sentry_traces_sampler(sampling_context):
        # Inherit parent sampling decision
        if sampling_context["parent_sampled"] is not None:
            return sampling_context["parent_sampled"]

        # Don't need to sample health checks
        if sampling_context.get("wsgi_environ", {}).get("PATH_INFO", "") == "/health":
            return 0
        
        # Sample everything else
        return 1

    sentry_sdk.init(
        **sentry_config,
        integrations=[sentry_logging],

        traces_sampler=sentry_traces_sampler,

        enable_tracing=True,
    )
else:
    logging.info("No Sentry DSN found. Skipping Sentry setup.")

def split_dsn(dsn):
    """
    Split a DSN into its components.
    """
    parsed = urllib.parse.urlparse(dsn)
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname,
        "port": parsed.port,
        "project_id": parsed.path.strip("/"),
        "public_key": parsed.username,
        "secret_key": parsed.password,
    }

# Parse the DSNs into their components
for dsn in ALLOWED_SENTRY_DSNS:
    parsed_dsn = split_dsn(dsn)
    ALLOWED_SENTRY_HOSTS.add(parsed_dsn["host"])
    ALLOWED_SENTRY_PROJECT_IDS.add(parsed_dsn["project_id"])
    

app = flask.Flask(__name__)
CORS(app)
state = {
    "sentry_cron_last_ping_time": 0,
    "num_tunnel_requests_received": 0,
    "num_tunnel_requests_success": 0,
}

@app.route("/tunnel", methods=["POST"])
def tunnel():
    state["num_tunnel_requests_received"] += 1

    try:
        logging.debug(f"Request headers: {request.headers}")
        logging.debug(f"Remote addr: {request.remote_addr}")
        if request.headers.getlist("Cf-Connecting-Ip"):
            remote_addr = request.headers.getlist("Cf-Connecting-Ip")[0]
        elif request.headers.getlist("X-Forwarded-For"):
            remote_addr = request.headers.getlist("X-Forwarded-For")[0] 
        else:
            remote_addr = request.remote_addr

        envelope = flask.request.data
        piece = envelope.split(b"\n")[0].decode("utf-8")
        header = json.loads(piece)
        dsn = urllib.parse.urlparse(header.get("dsn"))

        if dsn.hostname not in ALLOWED_SENTRY_HOSTS:
            raise Exception(f"Invalid Sentry host: {dsn.hostname}")

        project_id = dsn.path.strip("/")
        if project_id not in ALLOWED_SENTRY_PROJECT_IDS:
            raise Exception(f"Invalid Project ID: {project_id}")

        url = f"https://{dsn.hostname}/api/{project_id}/envelope/"
        headers = {
            "Content-Type": "application/x-sentry-envelope",
            "X-Forwarded-For": remote_addr,
        }
        logging.debug(f"Forwarding envelope to {dsn.hostname} for project {project_id}. {url=} {headers=}")

        requests.post(url=url, data=envelope, headers=headers)
    except Exception as e:
        # handle exception in your preferred style,
        # e.g. by logging or forwarding to Sentry
        logging.exception(e)
    else:
        state["num_tunnel_requests_success"] += 1

    return {}

@app.route("/build-info")
def build_info():
    return BUILD_INFO

@app.route("/health")
def health():
    current_time = time.time()
    # Ping Sentry at least every minute. Using a 30s buffer to be safe.
    if IS_SENTRY_ENABLED and current_time - state["sentry_cron_last_ping_time"] > 30:
        state["sentry_cron_last_ping_time"] = current_time
        ping_sentry()

    return "OK"

# Sentry CRON docs: https://docs.sentry.io/platforms/python/crons/
@monitor(monitor_slug='sentry-tunnel', monitor_config={
    "schedule": { "type": "interval", "value": 1, "unit": "minute" },
    "checkin_margin": 5, # minutes
    "max_runtime": 1, # minutes
    "failure_issue_threshold": 1,
    "recovery_threshold": 2,
})
def ping_sentry():
    logging.info("Pinged Sentry CRON")

@app.get("/runtime-info")
def read_runtime_info():
    return {
        "sentry_enabled": IS_SENTRY_ENABLED,
        "sentry_sdk_version": sentry_sdk.VERSION,
        "deployment_environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "unknown"),
        "sentry_cron_last_ping_time": state["sentry_cron_last_ping_time"],
        "num_tunnel_requests_received": state["num_tunnel_requests_received"],
        "num_tunnel_requests_success": state["num_tunnel_requests_success"],
    }

if __name__ == "__main__":
    from waitress import serve
    serve(app, host=HOST, port=PORT)
