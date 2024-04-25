FROM python:3.11.5-slim

# Pass information about the build to the container
ARG DOCKER_METADATA_OUTPUT_JSON='{}'
ENV DOCKER_METADATA_OUTPUT_JSON=${DOCKER_METADATA_OUTPUT_JSON}

RUN apt-get update && apt-get install -y curl

COPY requirements.txt /app/
WORKDIR /app

RUN pip install -r requirements.txt

COPY . /app

HEALTHCHECK --interval=10s --timeout=5s --retries=3 CMD curl --fail http://localhost:5000/health || exit 1

CMD ["python", "/app/app.py"]
