FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ /app/

EXPOSE 5000

CMD ["python", "main.py"]
