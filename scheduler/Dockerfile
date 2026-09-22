FROM python:3.10-slim

WORKDIR /app

# Installa le dipendenze
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia l'intera cartella src dentro /app/src
COPY src/ /app/src/

# Imposta il PYTHONPATH così Python trova i moduli (config, utils, core)
ENV PYTHONPATH=/app/src

# Cambia la directory di lavoro in src per eseguire il main
WORKDIR /app/src

# Esegui l'applicativo senza buffer per i log immediati
CMD ["python", "-u", "main.py"]