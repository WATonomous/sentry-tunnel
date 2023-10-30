import json
import os
import urllib

import flask
import requests
from flask_cors import CORS
import logging

ALLOWED_SENTRY_HOSTS = [s.strip() for s in os.environ.get("ALLOWED_SENTRY_HOSTS", "").split(",")]
ALLOWED_SENTRY_PROJECT_IDS = [s.strip() for s in os.environ.get("ALLOWED_SENTRY_PROJECT_IDS", "").split(",")]
LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG")
PORT = os.environ.get("PORT", 5000)
HOST = os.environ.get("HOST", "0.0.0.0")

logging.basicConfig(level=LOG_LEVEL)

app = flask.Flask(__name__)
CORS(app)


@app.route("/tunnel", methods=["POST"])
def tunnel():
    try:
        envelope = flask.request.data
        piece = envelope.split(b"\n")[0].decode("utf-8")
        header = json.loads(piece)
        dsn = urllib.parse.urlparse(header.get("dsn"))

        if dsn.hostname not in ALLOWED_SENTRY_HOSTS:
            raise Exception(f"Invalid Sentry host: {dsn.hostname}")

        project_id = dsn.path.strip("/")
        if project_id not in ALLOWED_SENTRY_PROJECT_IDS:
            raise Exception(f"Invalid Project ID: {project_id}")

        logging.debug(f"Forwarding envelope to {dsn.hostname} for project {project_id}")
        url = f"https://{dsn.hostname}/api/{project_id}/envelope/"

        requests.post(url=url, data=envelope, headers={"Content-Type": "application/x-sentry-envelope"})
    except Exception as e:
        # handle exception in your preferred style,
        # e.g. by logging or forwarding to Sentry
        logging.exception(e)

    return {}


if __name__ == "__main__":
    from waitress import serve
    serve(app, host=HOST, port=PORT)
