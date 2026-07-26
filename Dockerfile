FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY . .

RUN pip install --upgrade pip && \
    pip install .

EXPOSE 8000

CMD ["uvicorn", "customer360.api.main:app", "--host", "0.0.0.0", "--port", "8000"]