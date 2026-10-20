FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY plot_entanglement.py plot_sla.py .
# Cartella di output per salvare i grafici (da montare come volume)
RUN mkdir /app/output
ENTRYPOINT ["python", "plot_sla.py"]