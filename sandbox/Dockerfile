FROM python:3.11-slim
WORKDIR /code
RUN pip install --no-cache-dir pytest
# Code is injected at runtime via docker cp / put_archive — not baked in.
CMD ["pytest", "--tb=short", "-v", "--no-header"]
