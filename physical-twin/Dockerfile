FROM python:3.10-slim
WORKDIR /app
RUN pip install --no-cache-dir paho-mqtt
COPY sim_app.py .
CMD ["python", "sim_app.py"]