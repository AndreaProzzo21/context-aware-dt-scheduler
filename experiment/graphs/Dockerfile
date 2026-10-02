FROM python:3.9-slim

WORKDIR /app

# Installa le librerie necessarie
RUN pip install --no-cache-dir matplotlib numpy

# Copia lo script nel container
COPY sla_projection.py .

# Esegue lo script
CMD ["python", "sla_projection.py"]