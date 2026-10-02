import os
import time
import json
import threading
import random
import paho.mqtt.client as mqtt
from prometheus_client import start_http_server, Gauge

# Variabili d'ambiente
POD_NAME = os.getenv("POD_NAME", "unknown-pod")
NAMESPACE = os.getenv("NAMESPACE", "default")
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto-broker.default.svc.cluster.local")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "machine/01/data")

# Parametro configurabile: dopo quanti secondi inizia il degrado (es. 300 = 5 min)
DEGRADATION_START_SEC = float(os.getenv("DEGRADATION_START_SEC", "300.0"))

# ---------------------------------------------------------
# SETUP PROMETHEUS METRICS
# ---------------------------------------------------------
LABELS = ['pod', 'namespace']
pt_dt_delay_gauge = Gauge('pt_dt_delay', 'Physical to DT delay in ms', LABELS)
dt_comp_delay_gauge = Gauge('dt_comp_delay', 'DT computation delay in ms', LABELS)
entanglement_gauge = Gauge('entanglement', 'Total entanglement delay in ms', LABELS)

clock_offset = None
APP_START_TIME = time.time()

def compute_active_load():
    """Simula il processamento bloccando il thread per circa 100ms."""
    start = time.time()
    num = 2
    while (time.time() - start) < 0.100:
        is_prime = True
        for i in range(2, int(num ** 0.5) + 1):
            if num % i == 0:
                is_prime = False
                break
        num += 1
    return (time.time() - start) * 1000

def process_digital_twin_task(payload, recv_time):
    global clock_offset
    
    try:
        raw_send_time = payload.get("timestamp_ms", recv_time)
        
        if clock_offset is None:
            clock_offset = (recv_time - raw_send_time) - 5.0
            print(f"[*] Calibrazione Clock iniziale completata. Offset: {clock_offset:.1f} ms", flush=True)
            
        real_send_time = raw_send_time + clock_offset
        
        # 1. Calcolo ritardo di rete reale
        pt_dt_delay = max(0, recv_time - real_send_time) 
        
        # 2. Calcolo computazionale
        comp_delay = compute_active_load()
        
        # -------------------------------------------------------------
        # CHAOS TESTING INJECTION REALISTICO
        # Dopo DEGRADATION_START_SEC aggiunge latenza variabile + spike
        # -------------------------------------------------------------
        uptime = time.time() - APP_START_TIME
        if uptime > DEGRADATION_START_SEC:
            base_degradation = 350.0  # Latenza base degradata
            jitter = random.uniform(-40.0, 60.0)  # Fluttuazione standard
            
            # 20% di probabilità di avere uno spike elevato
            spike = random.uniform(100.0, 200.0) if random.random() < 0.2 else 0.0
            
            pt_dt_delay += (base_degradation + jitter + spike)
        
        # 3. Entanglement
        entanglement = pt_dt_delay + comp_delay
        
        # Aggiorna metriche
        pt_dt_delay_gauge.labels(pod=POD_NAME, namespace=NAMESPACE).set(pt_dt_delay)
        dt_comp_delay_gauge.labels(pod=POD_NAME, namespace=NAMESPACE).set(comp_delay)
        entanglement_gauge.labels(pod=POD_NAME, namespace=NAMESPACE).set(entanglement)
        
        if uptime > DEGRADATION_START_SEC:
            print(f"[{POD_NAME}] ⚠️ DEGRADO SIMULATO ATTIVO! PT_DT: {pt_dt_delay:.1f}ms | Comp: {comp_delay:.1f}ms | Ent: {entanglement:.1f}ms", flush=True)
        else:
            print(f"[{POD_NAME}] Msg elaborato. PT_DT: {pt_dt_delay:.1f}ms | Comp: {comp_delay:.1f}ms | Entanglement: {entanglement:.1f}ms", flush=True)
        
    except Exception as e:
        print(f"Errore nel thread di calcolo: {e}", flush=True)

def on_message(client, userdata, msg):
    recv_time = time.time() * 1000 
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        threading.Thread(target=process_digital_twin_task, args=(payload, recv_time), daemon=True).start()
    except Exception as e:
        print(f"Errore parsing: {e}", flush=True)

def main():
    print(f"Starting Digital Twin [{POD_NAME}] in namespace [{NAMESPACE}]", flush=True)
    print(f"Degradation timer set to start after {DEGRADATION_START_SEC} seconds.", flush=True)
    start_http_server(8000) 
    
    client = mqtt.Client()
    client.on_message = on_message
    
    while True:
        try:
            client.connect(MQTT_BROKER, 1883, 60)
            break
        except Exception as e:
            print(f"In attesa del broker... {e}", flush=True)
            time.sleep(2)
            
    client.subscribe(MQTT_TOPIC)
    print("Connesso al broker e in ascolto!", flush=True)
    client.loop_forever()

if __name__ == "__main__":
    main()