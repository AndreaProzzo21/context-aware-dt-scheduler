# README - Digital Twin Workloads & Advanced Chaos Testing

## Panoramica e Contesto Architetturale

Questa cartella contiene l'implementazione software e i manifest Kubernetes dei **Digital Twin (DT)** impiegati nelle fasi avanzate della sperimentazione della tesi.

A differenza della fase preliminare (basata su semplici Deployment stateless), i Digital Twin sono qui modellati come istanze persistenti e stateful. Ciascun DT si connette a un broker MQTT centralizzato per ricevere i flussi di telemetria in tempo reale dalla controparte fisica (`physical-twin/`), elabora i dati localmente calcolando l'indice di sincronizzazione cyber-fisica (*Entanglement*), ed espone metriche granulari per consentire al **Custom Scheduler** di intercettare i degradi prestazionali e **triggerare automaticamente le migrazioni (rescheduling)** dei carichi.

---

## Tipologie di Digital Twin e Chaos Testing

Il codice sorgente prevede tre varianti specializzate di DT, progettate per replicare diverse condizioni operative e stress test controllati:

1. **`dt_app.py` (Versione Standard / Baseline):**
Esegue l'elaborazione dei pacchetti telemetrici con un carico computazionale costante e nominale. Viene utilizzato come riferimento stabile per valutare le prestazioni in condizioni ottimali.
2. **`dt_cpu.py` (Degrado Computazionale - Chaos Testing):**
Integra un meccanismo di stress dinamico basato sul tempo di uptime. Superata una soglia prestabilita (es. 100 secondi di attività), forza un algoritmo di calcolo intensivo (ricerca di numeri primi) che innalza il tempo di elaborazione da 100ms a 500ms, simulando una situazione di CPU throttling, saturazione delle risorse di calcolo sul nodo edge o interferenze da parte di altri container co-locati.
3. **`dt_latency.py` (Degrado di Rete):**
Progettato per evidenziare e stressare il sistema in presenza di fluttuazioni o ritardi anomali nella ricezione dei messaggi MQTT dal broker, isolando l'impatto della latenza di rete sulle performance del digital twin.

---

## Metriche Esportate e Formalizzazione dell'Entanglement

Ogni pod Digital Twin avvia un server HTTP integrato sulla porta **`8000`**, sfruttando la libreria `prometheus_client` per esporre le seguenti metriche custom conformemente allo standard Prometheus:

* **`pt_dt_delay` (Physical-to-Digital Twin Delay):** Rappresenta il ritardo di rete e trasmissione dei dati, calcolato compensando dinamicamente l'offset iniziale del clock tra la sorgente fisica e il pod ricevente.
* **`dt_comp_delay` (Computation Delay):** Quantifica il tempo effettivo impiegato dal thread interno del DT per processare il payload e completare il ciclo di calcolo attivo (`compute_active_load`).
* **`entanglement` (Overall Digital Twin Entanglement - ODTE):** L'indice sintetico complessivo, calcolato come la somma algebrica delle componenti di rete e computazionali.

---

## Configurazione dei Digital Twin tramite StatefulSet e Annotazioni

Per garantire che il middleware di scheduling possa gestire correttamente il ciclo di vita del Digital Twin (preservandone lo stato in caso di migrazione e rendendo possibile il retrieve dell'entanglement da Prometheus), l'utilizzo di un **StatefulSet** è un requisito obbligatorio.

Le decisioni dello scheduler sono guidate dalle **annotazioni dichiarative** inserite nel manifest, le quali definiscono la strategia di posizionamento, la soglia critica di tolleranza all'entanglement e i requisiti hardware stringenti.

Di seguito viene fornito il manifest di riferimento completo, configurato per prelevare direttamente l'immagine container ufficiale da Docker Hub (`aprozzo/dt-entanglement:v3`):

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: twin-machine-02
  namespace: default
spec:
  serviceName: "twin-machine-02"
  replicas: 1
  selector:
    matchLabels:
      app: digital-twin
  template:
    metadata:
      labels:
        app: digital-twin
      annotations:
        # Configurazione dello scraping delle metriche per Prometheus
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
        
        # Strategie e parametri operativi letti dal Custom Scheduler
        iot-scheduler/strategy: "minimize-latency"
        iot-scheduler/entanglement-threshold-ms: "450"
        iot-scheduler/hw-required: "amd64"
    spec:
      # Nome dello scheduler custom responsabile della gestione di questo pod
      schedulerName: iot-twin-scheduler
      containers:
      - name: twin
        image: aprozzo/dt-entanglement:v3
        imagePullPolicy: Always
        ports:
        - name: metrics
          containerPort: 8000
        env:
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        - name: MQTT_BROKER
          value: "mosquitto-broker.default.svc.cluster.local"

```

---

## Guida al Deploy

### 1. Prerequisiti d'Ambiente

* Un cluster Kubernetes attivo con il Custom Scheduler configurato e in esecuzione (vedi cartella `deploy/`).
* Un'istanza di Prometheus (o Prometheus Operator) configurata nel cluster.
* Un broker MQTT (es. Mosquitto) raggiungibile internamente al cluster.

### 2. Configurazione del Monitoraggio (`twin-pod-monitor.yaml`)

Per permettere a Prometheus di scoprire automaticamente i pod dei Digital Twin e raccogliere le metriche di entanglement (`pt_dt_delay`, `dt_comp_delay`, `entanglement`), applica la risorsa di monitoraggio nel cluster:

```bash
kubectl apply -f twin-pod-monitor.yaml

```

Nota: La stessa risorsa è presente in **/monitoring-stack**. Applicarla soltanto una volta dopo aver settato lo stack di monitoraggio e i twin.

### 3. Recupero Automatico dell'Immagine

Le immagini dei Digital Twin sono già compilate e ospitate sul repository Docker Hub (`aprozzo/dt-entanglement:v3`). Il cluster Kubernetes provvederà a scaricarle autonomamente grazie alla policy `imagePullPolicy: Always`, azzerando la necessità di build locali.

### 4. Esecuzione dei Test con Chaos Injection

A seconda dello scenario di test che si intende replicare (degrado computazionale o di rete), applicare il rispettivo manifest StatefulSet:

* **Per avviare il test di stress sulla CPU:**
```bash
kubectl apply -f statefulset_cpu.yaml

```


* **Per avviare il test di stress sulla rete:**
```bash
kubectl apply -f statefulset_net.yaml

```



### 5. Monitoraggio del comportamento dello Scheduler

1. **Verifica dello scraping:** Controlla l'interfaccia di Prometheus per accertarti che le metriche dei DT vengano raccolte correttamente.

2. **Osservazione delle migrazioni dinamiche:** Monitorando i log del custom scheduler o lo stato dei pod (`kubectl get pods -o wide`), noterai che, al superamento della soglia dichiarata nelle annotazioni (es. `iot-scheduler/entanglement-threshold-ms: "450"`), lo scheduler intercetterà il degrado attivando automaticamente la migrazione del StatefulSet verso un nodo più idoneo.