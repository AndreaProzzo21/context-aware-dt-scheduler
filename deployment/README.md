# README - Kubernetes Deployment Manifests (`deployment/`)

Questa cartella contiene i manifest YAML necessari per il provisioning e il corretto funzionamento del custom scheduler all'interno del cluster Kubernetes.

## Struttura della Cartella

* **`rbac.yaml`**: Configura i permessi di sicurezza (ServiceAccount, ClusterRole e ClusterRoleBinding) per permettere allo scheduler custom di interrogare l'API server di Kubernetes, monitorare i pod e assegnare i nodi (binding).
* **`scheduler-deployment.yaml`**: Definisce il Deployment effettivo dello scheduler come componente del control plane, specificando l'immagine del container, le variabili d'ambiente (es. l'endpoint di Prometheus) e associandoli al ServiceAccount dedicato.

---

## Istruzioni per il Deploy

Per installare ed avviare lo scheduler nel cluster, seguire questi passaggi in ordine sequenziale:

### 1. Applicare le configurazioni RBAC

Crea il ServiceAccount e i ruoli di autorizzazione necessari affinché lo scheduler abbia i permessi di lettura e scrittura sul cluster:

```bash
kubectl apply -f deployment/rbac.yaml

```

### 2. Eseguire il Deployment dello Scheduler

Avvia l'istanza dello scheduler nel namespace di sistema (o nel namespace di riferimento):

```bash
kubectl apply -f deployment/scheduler-deploy.yaml

```

### 3. Verificare lo stato del Pod

Controlla che il container dello scheduler sia correttamente in esecuzione (`Running`):

```bash
kubectl get pods -n kube-system -l app=iot-twin-scheduler

```

### 4. Controllare i Log

Per verificare l'effettivo avvio della logica di scheduling e la connessione con lo stack di monitoraggio:

```bash
kubectl logs -f deployment/iot-twin-scheduler -n kube-system

```