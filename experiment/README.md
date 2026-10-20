# README - Validazione dello Scheduler e Integrazione Telemetrica (Fase Preliminare)

Questa sezione raccoglie le prove sperimentali e i test preliminari condotti sulla prima versione dello scheduler custom. In questa fase iniziale, lo scheduler **non integrava ancora il monitoraggio dinamico dell'Entanglement Cyber-Fisico** (gli esperimenti sull'ODTE sono documentati nella sezione dedicata).

Di conseguenza, i Digital Twin (DT) e i workload sono stati gestiti tramite oggetti **Kubernetes Deployment** standard, anziché *StatefulSet*.

Nota: Gli esperimenti documentati in questa sezione corrispondono esattamente al percorso di test condotto dalla Phase 1 alla Phase 4 della tesi.

## Obiettivi dei Test

I test contenuti in questa cartella avevano il duplice obiettivo di:

1. **Validare il meccanismo di Decision-Making basato su Telemetria Esterna:** Verificare che lo scheduler custom fosse in grado di interrogare lo stack di monitoraggio (Prometheus) ed elaborare metriche in tempo reale (es. latenza ICMP/ping, carico/temperatura CPU, I/O su disco) per guidare il posizionamento dei pod.
2. **Validare l'Hardware e la Strategia tramite Annotazioni:** Verificare la capacità dello scheduler di interpretare correttamente le annotazioni presenti nei manifest dei manifest/Deployment, abbinando i vincoli dichiarativi del workload con le risorse hardware ed edge disponibili nel cluster.
3. **Valutazione del Trade-Off tra Criteri Decisionali Differenti:** Testare come lo scheduler effettua un bilanciamento (trade-off) dinamico tra criteri di decisione in contrasto tra loro (ad esempio, priorità alla latenza di rete vs. disponibilità di calcolo/I/O sul nodo).
4. **Test di Disaster Recovery in Scenari Critici:** Valutare la resilienza e il comportamento dello scheduler di fronte a guasti infrastrutturali, analizzando due scenari specifici:

Spegnimento di un nodo worker: Verifica del corretto rilevamento del guasto ed esecuzione della normale migrazione/rischeduling del pod su un nodo alternativo idoneo.

Outage di un intero sito/cluster locale: Gestione dell'interruzione di un sito che ospitava l'unico nodo dotato dei requisiti hardware specifici richiesti dal workload; in questo scenario si verifica che lo scheduler mantenga il pod nello stato di Pending in attesa del ripristino delle risorse idonee, evitando allocazioni errate o inconsistenti.

## Esecuzione (Phase 1 - Phase 3)

Prima di procedere con l'esecuzione delle singole fasi, assicurarsi che lo **scheduler custom sia attivo** nel cluster (o in esecuzione locale) e pronto a intercettare le richieste.

---

### Phase 1: Validazione del Decision-Making e Telemetria di Rete
* **Obiettivo:** Testare come il custom scheduler reagisce a un'iniezione di degrado di rete rispetto al comportamento dello scheduler standard di Kubernetes.
* **Passaggi:**
  1. **Iniezione del Degrado:** Applicare il ritardo di rete sintetico sul nodo target (es. `nodo-3`):
     ```bash
     kubectl apply -f baseline/fake-latency.yaml
     ```
  2. **Deploy del Digital Twin con Scheduler Standard:**
     ```bash
     kubectl apply -f baseline/baseline-deploy.yaml
     ```
  3. **Deploy del Digital Twin con Custom Scheduler:**
     ```bash
     kubectl apply -f baseline/baseline-scheduler.yaml
     ```
  4. **Verifica:** Il default scheduler potrebbe aver piazzato il pod su nodo 3, il custom scheduler ha evitato il piazzamento su nodo 3 (kubectl get pods -o wide)

---

### 🔹 Phase 2: Validazione Hardware e Annotazioni di Strategia
* **Obiettivo:** Verificare l'accoppiamento tra le annotazioni dichiarative del manifest e l'hardware reale dei nodi.
* **Passaggi:**
  1. **Apply del manifest:**
     ```bash
     kubectl apply -f hardware/dt-hardware-contstrained.yaml
     ```
  2. **Verifica:** Il custom scheduler deve avere deployato il twin sul nodo che presenta i requisiti specificati (gpu-edge, amd64)
     ```bash
     kubectl get pods -o wide
     ```

---

### 🔹 Phase 3: Valutazione del Trade-Off tra Criteri Decisionali
* **Obiettivo:** Testare la capacità dello scheduler di bilanciare tra network latency e saturazione CPU.
* **Passaggi:**
  1. **Configurazione dello Scenario:** Applichiamo un evento di saturazione CPU fittizio
     ```bash
     kubectl apply -f stress/phase3_stress.yaml
     ```
  2. **Deploy del Workload:**
     ```bash
     kubectl apply -f phase3-tradeoff.yaml
     ```
  3. **Verifica dello Scoring da log dello scheduler:** 
     ```bash
     kubectl logs -f deploy/iot-twin-scheduler -n kube-system
     ```
---