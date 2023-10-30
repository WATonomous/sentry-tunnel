FROM python:3.11.5-slim

COPY requirements.txt /app/
WORKDIR /app

RUN pip install -r requirements.txt

COPY . /app

CMD ["python", "/app/app.py"]
