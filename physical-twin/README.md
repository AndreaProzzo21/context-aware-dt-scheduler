# README - Physical Twin Simulator (`physical-twin/`)

Questa cartella contiene il codice e il Dockerfile per la simulazione della controparte fisica (**Physical Twin**). Il simulatore ha il compito di generare flussi di telemetria in tempo reale (come la temperatura dei sensori e timestamp di invio) e di pubblicarli su un broker MQTT centralizzato, alimentando così il Digital Twin nel cluster Kubernetes.

---

## Contenuti della Cartella

* **`sim_app.py`**: Script Python principale che si connette al broker MQTT e invia periodicamente un payload JSON contenente i dati simulati e il timestamp ad alta precisione.
* **`Dockerfile`**: Configurazione leggera basata su Python 3.10-slim per containerizzare il simulatore.

---

## Funzionamento del Payload

Il simulatore invia un messaggio al secondo (`time.sleep(1)`) sul topic MQTT configurato. Ogni payload include:

* **`msg_id`**: Progressivo del messaggio inviato.
* **`sensor_temp`**: Valore di temperatura simulato (es. `45.5`).
* **`timestamp_ms`**: **FONDAMENTALE** per il sistema; rappresenta l'istante esatto di generazione in millisecondi (`time.time() * 1000`), utilizzato dai Digital Twin per calcolare con precisione il ritardo di rete (`pt_dt_delay`).

---

## Istruzioni per il Build e l'Avvio

### 1. Build dell'Immagine Docker

Dalla cartella del physical-twin, compila l'immagine del simulatore:

```bash
docker build -t physical-twin-sim:latest .

```

### 2. Esecuzione del Container

Avvia il container configurando le variabili d'ambiente per puntare al broker MQTT di riferimento:

```bash
docker run -d \
  --name physical-twin \
  -e MQTT_BROKER="mosquitto-broker.default.svc.cluster.local" \
  -e MQTT_PORT="1883" \
  -e MQTT_TOPIC="machine/01/data" \
  physical-twin-sim:latest

```

### 3. Verifica dei Log

Per controllare che il simulatore si sia connesso correttamente al broker e stia pubblicando i dati di telemetria al ritmo di 1 messaggio al secondo:

```bash
docker logs -f physical-twin

```