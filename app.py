import json
import os
import urllib

import flask
from flask_cors import CORS
from flask import request
import logging
import requests
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration


ALLOWED_SENTRY_HOSTS = set([s.strip() for s in os.environ.get("ALLOWED_SENTRY_HOSTS", "").split(",") if s.strip()])
ALLOWED_SENTRY_PROJECT_IDS = set([s.strip() for s in os.environ.get("ALLOWED_SENTRY_PROJECT_IDS", "").split(",") if s.strip()])
ALLOWED_SENTRY_DSNS = set([s.strip() for s in os.environ.get("ALLOWED_SENTRY_DSNS", "").split(",") if s.strip()])
LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG")
PORT = os.environ.get("PORT", 5000)
HOST = os.environ.get("HOST", "0.0.0.0")
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

logging.basicConfig(level=LOG_LEVEL)
if SENTRY_DSN:
    logging.info("Sentry DSN provided, enabling Sentry SDK")
    sentry_logging = LoggingIntegration(
        level=logging.INFO,        # Capture info and above as breadcrumbs
        event_level=logging.ERROR  # Send errors as events
    )
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            sentry_logging,
        ],

        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production,
        traces_sample_rate=1.0,
    )
else:
    logging.info("No Sentry DSN provided, Sentry SDK disabled")

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

@app.route("/tunnel", methods=["POST"])
def tunnel():
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

    return {}

@app.route("/health")
def health():
    return "OK"

if __name__ == "__main__":
    from waitress import serve
    serve(app, host=HOST, port=PORT)
