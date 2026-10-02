import time
import json
import os
import paho.mqtt.client as mqtt

# Configurazioni tramite variabili d'ambiente
MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))  # <--- Aggiunta variabile per la porta
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "machine/01/data")

def main():
    client = mqtt.Client()
    try:
        # Usa la porta dinamica per la connessione
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        print(f"Simulatore fisico connesso a {MQTT_BROKER}:{MQTT_PORT}")
    except Exception as e:
        print(f"Errore connessione broker: {e}")
        return

    msg_id = 0
    while True:
        msg_id += 1
        # timestamp_ms è fondamentale per il calcolo del pt_dt_delay sul pod!
        payload = {
            "msg_id": msg_id,
            "sensor_temp": 45.5,
            "timestamp_ms": time.time() * 1000 
        }
        client.publish(MQTT_TOPIC, json.dumps(payload))
        print(f"[Simulatore] Inviato msg {msg_id}: {payload}")
        time.sleep(1) # Un messaggio al secondo

if __name__ == "__main__":
    main()