FROM python:3.11-slim

# Metadata
LABEL maintainer="fb-token-app"
LABEL description="Facebook Cookie to Access Token Extractor"

# Python optimize + no pyc
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Working directory
WORKDIR /app

# Dependencies pehle install karo (caching ke liye)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Script copy karo
COPY fb_token.py .

# Non-root user (security)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Interactive script hai, so CMD sirf script chalaye
CMD ["python", "fb_token.py"]
