FROM python:3.10-slim
WORKDIR /app
RUN pip install --no-cache-dir paho-mqtt prometheus-client
COPY dt_app.py dt_latency.py dt_cpu.py .
CMD ["python", "dt_latency.py"]