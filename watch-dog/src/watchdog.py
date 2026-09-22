"""
entanglement-watchdog
======================
Componente SEPARATO dallo scheduler (iot_twin_scheduler.py): non lo importa,
non lo modifica, non ne condivide lo stato. Un processo indipendente, con un
suo Deployment e un suo RBAC (più ristretto di quello dello scheduler).

Monitora periodicamente l'"entanglement" (allineamento) tra ogni Digital Twin
in esecuzione e la sua controparte fisica, misurato dal twin stesso e esposto
via Prometheus come tre metriche in millisecondi:
  - pt_dt_delay: ritardo tra invio del messaggio MQTT dal dispositivo fisico e
    ricezione da parte del Digital Twin (calcolato e riportato dal twin).
  - dt_comp_delay: tempo che il Digital Twin impiega a processare il dato e
    aggiornare il proprio stato interno.
  - entanglement: somma delle due (pt_dt_delay + dt_comp_delay). È questa la
    metrica confrontata con la soglia.

Se l'entanglement di un twin supera la soglia in modo SOSTENUTO (non un
singolo campione rumoroso), il watchdog:
  1. Emette un Kubernetes Event sul pod (preavviso, visibile con
     `kubectl describe pod`) e ATTENDE un periodo di grazia, senza agire.
  2. Solo se la condizione persiste anche dopo il preavviso, elimina il pod.

PERCHÉ "ELIMINA" E NON "RI-BINDA": una PodBinding è un'operazione one-shot,
valida solo per un pod ancora Pending (senza spec.nodeName). Un pod già
Running non può essere ri-bindato a un altro nodo: l'unico modo per
"rischedularlo" è cancellarlo e lasciare che il suo controller lo ricrei. Il
nuovo pod genera un evento ADDED che passa di nuovo per iot_twin_scheduler.py,
che lo ripiazza con la STESSA logica di sempre (strategy/hw-required/
strategy-target letti dal template del pod), senza bisogno di alcuna modifica
lì: questo componente decide solo SE far ricreare un twin, mai DOVE.

PREREQUISITO: i Digital Twin vanno gestiti con una StatefulSet (non una
Deployment o un Pod nudo). Motivo: la StatefulSet garantisce un nome pod
stabile (es. "twin-a-0") anche dopo la ricreazione, mentre una Deployment
genera ogni volta un suffisso casuale nuovo. Questo watchdog correla le
metriche Prometheus al pod tramite la label "pod" (assegnata automaticamente
da Prometheus con la Kubernetes service discovery standard su ruolo "pod"):
se il nome cambiasse ad ogni riavvio, la soglia "per quel determinato twin"
perderebbe la sua identità tra un'istanza e la successiva.

ANNOTATION LETTE SUL POD (stesso namespace di quelle dello scheduler):
  - iot-scheduler/entanglement-threshold-ms: soglia specifica per questo twin
    (in ms). Se assente, si usa DEFAULT_ENTANGLEMENT_THRESHOLD_MS.
  - iot-scheduler/entanglement-policy: "active" (default) | "disabled". Un
    twin con "disabled" viene ignorato dal watchdog (mai rischedulato per
    entanglement, anche se la metrica esiste e supera la soglia).

RBAC MINIMO (volutamente più ristretto di quello dello scheduler): questo
processo legge/elimina pod ed emette eventi. NON legge nodi, NON crea
pods/binding, NON legge il Metrics Server: non decide mai dove ripiazzare un
twin, solo se farlo ricreare.
"""

from kubernetes import client, config
import logging
import requests
import os
import time
import signal
import datetime

# --- CONFIGURAZIONE GENERALE ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
SCHEDULER_NAME = os.getenv("SCHEDULER_NAME", "iot-twin-scheduler")  # stesso valore dello scheduler
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-operated.monitoring.svc.cluster.local:9090")
PROMETHEUS_TIMEOUT = float(os.getenv("PROMETHEUS_TIMEOUT_SECONDS", "6"))

WATCHDOG_INTERVAL_SECONDS = float(os.getenv("WATCHDOG_INTERVAL_SECONDS", "20"))
SUSTAINED_CHECKS_REQUIRED = int(os.getenv("SUSTAINED_CHECKS_REQUIRED", "3"))
GRACE_PERIOD_SECONDS = float(os.getenv("GRACE_PERIOD_SECONDS", "60"))
COOLDOWN_SECONDS = float(os.getenv("COOLDOWN_SECONDS", "180"))
MAX_RESCHEDULES_PER_HOUR = int(os.getenv("MAX_RESCHEDULES_PER_HOUR", "5"))
DEFAULT_ENTANGLEMENT_THRESHOLD_MS = float(os.getenv("DEFAULT_ENTANGLEMENT_THRESHOLD_MS", "500"))

# --- ANNOTATION KEYS (lette sul pod, stesso "namespace" di quelle dello scheduler) ---
ANNOTATION_ENTANGLEMENT_THRESHOLD = 'iot-scheduler/entanglement-threshold-ms'
ANNOTATION_ENTANGLEMENT_POLICY = 'iot-scheduler/entanglement-policy'  # "active" (default) | "disabled"

# --- STATO GLOBALE (in-memory, per pod tracciato tramite (namespace, nome)) ---
_decay_streak = {}       # {(namespace, pod_name): numero di controlli consecutivi sopra soglia}
_warned_at = {}           # {(namespace, pod_name): timestamp del preavviso}
_last_action_at = {}      # {(namespace, pod_name): timestamp dell'ultima rischedulazione (cooldown)}
_recent_actions = []      # [timestamp, ...] azioni globali nell'ultima ora (rate limit)

_shutdown_requested = False


def _handle_shutdown_signal(signum, frame):
    global _shutdown_requested
    logging.info(f"🛑 Ricevuto segnale {signum}, chiusura in corso dopo il ciclo corrente...")
    _shutdown_requested = True


signal.signal(signal.SIGTERM, _handle_shutdown_signal)
signal.signal(signal.SIGINT, _handle_shutdown_signal)


def get_running_twin_pods(v1):
    """
    Elenca i pod Running schedulati da questo scheduler (stesso schedulerName)
    e non esplicitamente esclusi dal watchdog (entanglement-policy=disabled).
    """
    pods = v1.list_pod_for_all_namespaces(field_selector="status.phase=Running")
    twins = []
    for pod in pods.items:
        if pod.spec.scheduler_name != SCHEDULER_NAME:
            continue
        annotations = pod.metadata.annotations or {}
        if annotations.get(ANNOTATION_ENTANGLEMENT_POLICY, 'active') == 'disabled':
            continue
        twins.append(pod)
    return twins


def get_entanglement_ms(pod_name, namespace):
    """
    Legge l'ultimo valore della metrica 'entanglement' per un pod specifico
    (filtrata per label 'pod' e 'namespace', assegnate da Prometheus via
    Kubernetes service discovery standard). Ritorna None se Prometheus non
    risponde o non ci sono ancora dati (es. il twin si è appena avviato).
    """
    query = f'avg(entanglement{{pod="{pod_name}", namespace="{namespace}"}})'
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={'query': query},
            timeout=PROMETHEUS_TIMEOUT
        )
        response.raise_for_status()
        results = response.json().get('data', {}).get('result', [])
        if not results:
            return None
        return float(results[0]['value'][1])
    except Exception as e:
        logging.warning(f"⚠️ Impossibile leggere l'entanglement per {namespace}/{pod_name}: {e}")
        return None


def _rate_limit_ok():
    """True se siamo ancora sotto MAX_RESCHEDULES_PER_HOUR nell'ultima ora (protezione anti-storm)."""
    now = time.time()
    global _recent_actions
    _recent_actions = [t for t in _recent_actions if now - t < 3600]
    return len(_recent_actions) < MAX_RESCHEDULES_PER_HOUR


def _emit_warning_event(v1, pod, reason, message):
    """Emette un Kubernetes Event di preavviso sul pod (visibile con kubectl describe pod)."""
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        event = client.CoreV1Event(
            metadata=client.V1ObjectMeta(
                generate_name=f"{pod.metadata.name}-entanglement-",
                namespace=pod.metadata.namespace,
            ),
            involved_object=client.V1ObjectReference(
                api_version="v1", kind="Pod",
                name=pod.metadata.name, namespace=pod.metadata.namespace,
                uid=pod.metadata.uid,
            ),
            reason=reason,
            message=message,
            type="Warning",
            source=client.V1EventSource(component="entanglement-watchdog"),
            first_timestamp=now,
            last_timestamp=now,
            count=1,
        )
        v1.create_namespaced_event(namespace=pod.metadata.namespace, body=event)
    except Exception as e:
        logging.warning(f"⚠️ Impossibile emettere l'Event di preavviso per {pod.metadata.name}: {e}")


def _reschedule_pod(v1, pod):
    """
    Elimina il pod per farlo ricreare dal suo controller (StatefulSet).
    NON è una PodBinding: un pod già Running non può essere ri-bindato, va
    ricreato da zero. Il nuovo pod passerà di nuovo per iot_twin_scheduler.py.
    """
    try:
        v1.delete_namespaced_pod(name=pod.metadata.name, namespace=pod.metadata.namespace)
        logging.info(f"🔁 Pod [{pod.metadata.namespace}/{pod.metadata.name}] eliminato per rischedulazione.")
        return True
    except client.ApiException as e:
        logging.error(f"❌ Impossibile eliminare il pod {pod.metadata.name} per la rischedulazione: {e}")
        return False


def evaluate_pod(v1, pod):
    """
    Valuta un singolo twin: legge l'entanglement, applica isteresi (controlli
    sostenuti), preavviso (Event + grace period) e infine, se la condizione
    persiste, la rischedulazione. Se il twin recupera in QUALSIASI momento
    prima della cancellazione effettiva (anche durante il grace period),
    l'azione viene annullata automaticamente.
    """
    key = (pod.metadata.namespace, pod.metadata.name)
    pod_name = pod.metadata.name
    namespace = pod.metadata.namespace
    annotations = pod.metadata.annotations or {}

    # Cooldown: appena rischedulato, non ricontrollarlo ancora
    last_action = _last_action_at.get(key)
    if last_action and (time.time() - last_action) < COOLDOWN_SECONDS:
        return

    threshold = float(annotations.get(ANNOTATION_ENTANGLEMENT_THRESHOLD, DEFAULT_ENTANGLEMENT_THRESHOLD_MS))
    value = get_entanglement_ms(pod_name, namespace)

    if value is None:
        # Nessun dato: il twin non sta ancora riportando (es. appena avviato).
        # Non penalizziamo: azzeriamo lo streak per evitare falsi positivi.
        _decay_streak.pop(key, None)
        _warned_at.pop(key, None)
        return

    if value <= threshold:
        if key in _decay_streak or key in _warned_at:
            logging.info(
                f"✅ Entanglement rientrato per {namespace}/{pod_name}: "
                f"{value:.1f}ms (soglia {threshold:.0f}ms)"
            )
        _decay_streak.pop(key, None)
        _warned_at.pop(key, None)
        return

    # Sopra soglia: incrementa lo streak di controlli consecutivi
    streak = _decay_streak.get(key, 0) + 1
    _decay_streak[key] = streak
    logging.info(
        f"📉 Entanglement sopra soglia per {namespace}/{pod_name}: {value:.1f}ms > {threshold:.0f}ms "
        f"(controllo consecutivo {streak}/{SUSTAINED_CHECKS_REQUIRED})"
    )

    if streak < SUSTAINED_CHECKS_REQUIRED:
        return  # non ancora un degrado sostenuto, potrebbe essere un blip

    warned_at = _warned_at.get(key)
    if warned_at is None:
        # Primo superamento sostenuto: emettiamo il preavviso, NON agiamo ancora.
        _emit_warning_event(
            v1, pod, "EntanglementDecayed",
            f"Entanglement a {value:.1f}ms, sopra la soglia di {threshold:.0f}ms da "
            f"{streak} controlli consecutivi. Rischedulazione tra {GRACE_PERIOD_SECONDS:.0f}s se persiste."
        )
        _warned_at[key] = time.time()
        logging.warning(
            f"⚠️ Preavviso emesso per {namespace}/{pod_name}, "
            f"grace period di {GRACE_PERIOD_SECONDS:.0f}s in corso..."
        )
        return

    if (time.time() - warned_at) < GRACE_PERIOD_SECONDS:
        return  # ancora dentro il periodo di grazia: aspettiamo

    if not _rate_limit_ok():
        logging.warning(
            f"🚦 Rischedulazione di {namespace}/{pod_name} rimandata: raggiunto il limite di "
            f"{MAX_RESCHEDULES_PER_HOUR}/ora sull'intero cluster."
        )
        return

    if _reschedule_pod(v1, pod):
        _last_action_at[key] = time.time()
        _recent_actions.append(time.time())
        _decay_streak.pop(key, None)
        _warned_at.pop(key, None)


def _cleanup_stale_state(current_keys):
    """Rimuove dallo stato in-memory i pod non più presenti (igiene, evita crescita illimitata)."""
    for store in (_decay_streak, _warned_at, _last_action_at):
        for key in list(store.keys()):
            if key not in current_keys:
                store.pop(key, None)


def main():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    v1 = client.CoreV1Api()
    logging.info(
        f"🚀 Starting entanglement-watchdog - monitoro i twin di [{SCHEDULER_NAME}] "
        f"ogni {WATCHDOG_INTERVAL_SECONDS:.0f}s..."
    )

    while not _shutdown_requested:
        try:
            twins = get_running_twin_pods(v1)
            current_keys = {(p.metadata.namespace, p.metadata.name) for p in twins}
            _cleanup_stale_state(current_keys)

            for pod in twins:
                try:
                    evaluate_pod(v1, pod)
                except Exception as e:
                    logging.error(
                        f"❌ Errore imprevisto valutando {pod.metadata.namespace}/{pod.metadata.name}: {e}",
                        exc_info=True
                    )
        except Exception as e:
            logging.error(f"❌ Errore imprevisto nel ciclo del watchdog: {e}", exc_info=True)

        # Attesa interrompibile, per rispondere velocemente a SIGTERM/SIGINT
        for _ in range(max(1, int(WATCHDOG_INTERVAL_SECONDS))):
            if _shutdown_requested:
                break
            time.sleep(1)

    logging.info("👋 entanglement-watchdog terminato correttamente (graceful shutdown).")


if __name__ == '__main__':
    main()