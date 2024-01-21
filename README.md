# Sentry Tunnel

This repo is derived from the [official example](https://github.com/getsentry/examples/tree/66da5f8c9559f64f1bfa57f8dd9b0731f75cd0e9/tunneling/python).

```bash
docker build -t sentry-tunnel .
docker run --rm -it --name sentry-tunnel -v $(pwd):/app -e ALLOWED_SENTRY_HOSTS=o123123123.ingest.sentry.io -e ALLOWED_SENTRY_PROJECT_IDS=456456456 -e PORT=5001 -p 5001:5001 sentry-tunnel
```

Below is the original README:


# Tunnel events through a Python Flask app

This example shows how you can use [Flask](https://flask.palletsprojects.com) to proxy events to Sentry.

The app always returns with status code `200`, even if the request to Sentry failed, to prevent brute force guessing of allowed configuration options.

## To run this example:

1. Install requirements (preferably in some [venv](https://docs.python.org/3/library/venv.html)):  
  `pip install -r requirements.txt`
2. Adjust `sentry_host` and `known_project_ids` in the `app.py` to your needs
3. Run the app with e.g.: `flask run`
4. Send sentry event to `http://localhost:5000/bugs`, e.g. via the test html mentioned at [examples/tunneling](../README.md)
