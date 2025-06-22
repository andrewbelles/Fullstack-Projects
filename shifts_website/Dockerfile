FROM python:3.12-slim AS base 

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
  && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PIP_NO_CACHE_DIR=1 \
  POETRY_VERSION=0 

WORKDIR /srv/app 
COPY requirements.txt .
RUN pip install -r requirements.txt 

FROM base AS final 

COPY . .

ENV PORT=8080
EXPOSE 8080 

CMD ["gunicorn", "-w", "4", "-b", ":8080", "wsgi:app"]
