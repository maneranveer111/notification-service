FROM python:3.11-slim
ARG GIT_SHA=dev
ENV APP_VERSION=$GIT_SHA
RUN useradd -m -u 1000 app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER app
