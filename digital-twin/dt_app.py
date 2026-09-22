import os
import time
import json
import threading
import paho.mqtt.client as mqtt
from prometheus_client import start_http_server, Gauge

# Variabili d'ambiente (il nome del pod e il namespace arriveranno dalle Downward API)
POD_NAME = os.getenv("POD_NAME", "unknown-pod")
NAMESPACE = os.getenv("NAMESPACE", "default")
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto-broker.default.svc.cluster.local")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "machine/01/data")

# ---------------------------------------------------------
# SETUP PROMETHEUS METRICS
# ---------------------------------------------------------
LABELS = ['pod', 'namespace']
pt_dt_delay_gauge = Gauge('pt_dt_delay', 'Physical to DT delay in ms', LABELS)
dt_comp_delay_gauge = Gauge('dt_comp_delay', 'DT computation delay in ms', LABELS)
entanglement_gauge = Gauge('entanglement', 'Total entanglement delay in ms', LABELS)

# Variabile globale per la compensazione del disallineamento dei clock (NTP drift)
clock_offset = None

def compute_active_load():
    """
    Simula il processamento del Digital Twin calcolando numeri primi.
    Gira in modo sincrono bloccando il thread corrente per circa 100ms.
    """
    start = time.time()
    num = 2
    # Esegue il loop finché non sono passati esattamente 0.1 secondi
    while (time.time() - start) < 0.100:
        is_prime = True
        for i in range(2, int(num ** 0.5) + 1):
            if num % i == 0:
                is_prime = False
                break
        num += 1
    return (time.time() - start) * 1000  # Ritorna il tempo consumato in ms

def process_digital_twin_task(payload, recv_time):
    """
    Funzione eseguita nel Thread separato. Si fa carico del lavoro pesante
    e della calibrazione temporale.
    """
    global clock_offset
    
    try:
        # Estrae il timestamp grezzo inviato dal simulatore fisico
        raw_send_time = payload.get("timestamp_ms", recv_time)
        
        # -------------------------------------------------------------
        # CALIBRAZIONE CLOCK (NTP Drift Compensation)
        # Al primo messaggio calcoliamo il disallineamento degli orologi.
        # Assumiamo che la latenza di rete base a riposo sia di circa 5 ms.
        # -------------------------------------------------------------
        if clock_offset is None:
            clock_offset = (recv_time - raw_send_time) - 5.0
            print(f"[*] Calibrazione Clock iniziale completata. Offset compensato: {clock_offset:.1f} ms", flush=True)
            
        # Applichiamo la compensazione per avere il tempo di invio reale "sincronizzato"
        real_send_time = raw_send_time + clock_offset
        
        # 1. Calcolo ritardo di rete reale (Transmission Delay)
        pt_dt_delay = max(0, recv_time - real_send_time) 
        
        # 2. Calcolo computazionale (blocca solo questo specifico worker thread)
        comp_delay = compute_active_load()
        
        # 3. Entanglement (La somma dei ritardi)
        entanglement = pt_dt_delay + comp_delay
        
        # Aggiorna le metriche Prometheus inserendo le label corrette
        pt_dt_delay_gauge.labels(pod=POD_NAME, namespace=NAMESPACE).set(pt_dt_delay)
        dt_comp_delay_gauge.labels(pod=POD_NAME, namespace=NAMESPACE).set(comp_delay)
        entanglement_gauge.labels(pod=POD_NAME, namespace=NAMESPACE).set(entanglement)
        
        print(f"[{POD_NAME}] Msg elaborato. PT_DT: {pt_dt_delay:.1f}ms | Comp: {comp_delay:.1f}ms | Entanglement: {entanglement:.1f}ms", flush=True)
        
    except Exception as e:
        print(f"Errore nel thread di calcolo: {e}", flush=True)

def on_message(client, userdata, msg):
    """
    Callback di ricezione MQTT.
    Iper-veloce e non bloccante: registra il timestamp e smazza il lavoro a un thread.
    """
    # Cattura il timestamp nel millisecondo esatto di ricezione dalla rete
    recv_time = time.time() * 1000 
    
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        
        # Delega il calcolo passandogli il payload e l'ora di ricezione.
        threading.Thread(target=process_digital_twin_task, args=(payload, recv_time), daemon=True).start()
        
    except Exception as e:
        print(f"Errore parsing messaggio in arrivo: {e}", flush=True)

def main():
    print(f"Starting Digital Twin [{POD_NAME}] in namespace [{NAMESPACE}]", flush=True)
    
    # Avvia l'exporter Prometheus sulla porta 8000
    start_http_server(8000) 
    
    client = mqtt.Client()
    client.on_message = on_message
    
    # Ritenta la connessione finché Mosquitto non è pronto
    while True:
        try:
            client.connect(MQTT_BROKER, 1883, 60)
            break
        except Exception as e:
            print(f"In attesa del broker {MQTT_BROKER}... {e}", flush=True)
            time.sleep(2)
            
    client.subscribe(MQTT_TOPIC)
    print("Connesso al broker e in ascolto (modalità non-bloccante multithread)!", flush=True)
    
    client.loop_forever()

if __name__ == "__main__":
    main()