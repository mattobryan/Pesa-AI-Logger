FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create directory for SQLite db and logs
RUN mkdir -p /data /app/runtime

# Expose port
EXPOSE 8000

# Start with gunicorn (production-grade)
CMD ["gunicorn", "pesa_logger.webhook:create_app()", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]