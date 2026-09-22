import time
import logging
import config.config as config
from utils.prometheus_utils import get_twin_metrics
from utils.kubernetes_utils import delete_pod, emit_warning_event

_decay_streak = {}
_warned_at = {}
_last_action_at = {}

def evaluate_pod_rca(v1, pod):
    pod_name = pod.metadata.name
    ns = pod.metadata.namespace
    pod_key = f"{ns}/{pod_name}"
    
    # Cooldown check
    if pod_key in _last_action_at and (time.time() - _last_action_at[pod_key]) < config.COOLDOWN_SECONDS:
        return

    threshold = float((pod.metadata.annotations or {}).get(config.ANNOTATION_ENTANGLEMENT_THRESHOLD, config.DEFAULT_ENTANGLEMENT_THRESHOLD_MS))
    
    metrics = get_twin_metrics(pod_name, ns)
    ent = metrics.get('entanglement')
    
    if ent is None: return

    if ent <= threshold:
        _decay_streak.pop(pod_key, None)
        _warned_at.pop(pod_key, None)
        return

    streak = _decay_streak.get(pod_key, 0) + 1
    _decay_streak[pod_key] = streak
    
    logging.warning(f"Entanglement anomaly [{pod_name}]: {ent:.1f}ms > {threshold}ms (streak: {streak}/{config.SUSTAINED_CHECKS_REQUIRED})")

    if streak >= config.SUSTAINED_CHECKS_REQUIRED:
        if pod_key not in _warned_at:
            _warned_at[pod_key] = time.time()
            msg = f"Entanglement sustained above {threshold}ms. Reschedule in {config.GRACE_PERIOD_SECONDS}s if unresolved."
            logging.info(f"Grace Period started for {pod_name}. Emitting Kubernetes Event.")
            emit_warning_event(v1, pod_name, ns, pod.metadata.uid, "EntanglementDecayed", msg)
            return
        
        if (time.time() - _warned_at[pod_key]) > config.GRACE_PERIOD_SECONDS:
            pt_dt = metrics.get('pt_dt_delay', 0)
            dt_comp = metrics.get('dt_comp_delay', 0)
            
            new_strategy = "minimize-latency"
            if dt_comp > pt_dt:
                logging.error(f"[RCA] Compute Degradation on {pod_name} (Comp:{dt_comp:.1f}ms > Net:{pt_dt:.1f}ms)")
                new_strategy = "minimize-cpu-load"
            else:
                logging.error(f"[RCA] Network Degradation on {pod_name} (Net:{pt_dt:.1f}ms > Comp:{dt_comp:.1f}ms)")
            
            with config.shared_lock:
                config.SHARED_OVERRIDES[pod_key] = new_strategy
                
            if delete_pod(v1, ns, pod_name):
                _decay_streak.pop(pod_key, None)
                _warned_at.pop(pod_key, None)
                _last_action_at[pod_key] = time.time()

def watchdog_loop(v1):
    logging.info(f"RCA Watchdog started. Scanning every {config.WATCHDOG_INTERVAL_SECONDS}s...")
    while not config.shutdown_requested:
        try:
            pods = v1.list_pod_for_all_namespaces(field_selector="status.phase=Running")
            twins = [p for p in pods.items if p.spec.scheduler_name == config.SCHEDULER_NAME]
            for pod in twins:
                evaluate_pod_rca(v1, pod)
        except Exception as e:
            logging.error(f"Watchdog error: {e}", exc_info=True)
            
        time.sleep(config.WATCHDOG_INTERVAL_SECONDS)