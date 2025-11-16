FROM python:3.11.5

WORKDIR /app

COPY . /app/

# Copy config file (use sample if prod config doesn't exist)
# Note: In production, mount config.json as volume or copy it during build
# COPY sample_config.json /app/sample_config.json

RUN pip install -r requirements.txt

# Expose web interface port
EXPOSE 5000

# Use sample config for testing, override with --config in docker run
CMD ["python3", "-u", "-m", "dealer", "--config", "config.json", "--local"]
