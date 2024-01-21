FROM python:3.11.5-slim

# Pass information about the build to the container
ARG DOCKER_METADATA_OUTPUT_JSON='{}'
ENV DOCKER_METADATA_OUTPUT_JSON=${DOCKER_METADATA_OUTPUT_JSON}

COPY requirements.txt /app/
WORKDIR /app

RUN pip install -r requirements.txt

COPY . /app

CMD ["python", "/app/app.py"]
