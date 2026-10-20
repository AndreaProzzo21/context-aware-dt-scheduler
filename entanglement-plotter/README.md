# README - Entanglement & System Availability Plotter (`entanglement-plotter/`)

Questa cartella raccoglie gli script e i file di configurazione necessari per interrogare lo stack di monitoraggio (Prometheus), elaborare le metriche di ritardo e generare i grafici ufficiali delle **Fasi 5 e 6** della tesi, focalizzati sull'Entanglement Cyber-Fisico e sulla *System Availability* comparata.

## Contenuti della Cartella

* **Script Python di Plotting:** Script dedicati all'interrogazione delle metriche di Prometheus (`pt_dt_delay` e `dt_comp_delay`) e alla generazione dei grafici.
* **`Dockerfile`:** Configurazione containerizzata per eseguire l'estrazione dei dati e il rendering dei grafici in un ambiente isolato e riproducibile.

---

## Metriche Analizzate

Gli script eseguono query automatizzate su Prometheus per estrarre e correlare i seguenti indicatori chiave:

* **`pt_dt_delay`**: Ritardo/latenza tra il Physical Asset (PA) e il rispettivo Digital Twin (DT).
* **`dt_comp_delay`**: Ritardo computazionale interno al ciclo di aggiornamento del Digital Twin.
* **Aggiornamento ODTE (Fase 5)**: Combinazione delle metriche per valutare la coerenza e la sincronizzazione dello stato cyber-fisico.
* **System Availability (Fase 6)**: Analisi comparativa della disponibilità di sistema raggiunta dal middleware rispetto alle baseline standard di Kubernetes sotto stress.

---

## Istruzioni per l'Esecuzione (Docker)

Per garantire la massima replicabilità dei grafici senza dipendenze locali di Python, l'intero flusso è incapsulato in un container Docker.

### 1. Modificare l'Entrypoint del Dockerfile

Per scegliere quale grafico generare (es. le curve di entanglement della Fase 5 o l'analisi di system availability della Fase 6), aprire il file **`Dockerfile`** e modificare lo script Python eseguito nell'istruzione `ENTRYPOINT` o `CMD`:

```dockerfile
# Esempio all'interno del Dockerfile
ENTRYPOINT ["python3", "plot_entanglement.py"]

```

*(Sostituisci `nome_script_desiderato.py` con lo script specifico che intendi eseguire, ad es. `plot_entanglement.py` o `plot_sla.py`).*

### 2. Build dell'immagine Docker

Dalla cartella principale del progetto o direttamente all'interno di `entanglement-plotter/`, compila il container:

```bash
docker build -t entanglement-plotter .

```

### 3. Avvio del Container ed Estrazione dei Grafici

Esegui il container passando (se necessario) le variabili d'ambiente per connetterti all'endpoint di Prometheus:

```bash
docker run --rm -v $(pwd)/output:/app/output -e PROMETHEUS_URL="http://<PROMETHEUS_IP>:9090" entanglement-plotter

```

* I grafici generati verranno salvati automaticamente nella cartella locale `/output` montata dal container.