import logging
import itertools
import config.config as config
from utils.prometheus_utils import get_prometheus_metric
from utils.kubernetes_utils import get_node_hw_tags, get_resource_usage_percent

_round_robin_cycle_cache = {}

def _normalize(values_dict):
    if not values_dict:
        return {}
    vals = list(values_dict.values())
    lo, hi = min(vals), max(vals)
    if hi == lo: return {k: 0.0 for k in values_dict}
    return {k: (v - lo) / (hi - lo) for k, v in values_dict.items()}

def _get_round_robin_node(candidate_nodes):
    key = frozenset(candidate_nodes.keys())
    if key not in _round_robin_cycle_cache:
        _round_robin_cycle_cache.clear()
        _round_robin_cycle_cache[key] = itertools.cycle(sorted(candidate_nodes.keys()))
    return next(_round_robin_cycle_cache[key])

def calculate_best_node(v1, nodes_dict, pod_name, namespace, annotations):
    pod_key = f"{namespace}/{pod_name}"
    
    with config.shared_lock:
        strategy = config.SHARED_OVERRIDES.get(pod_key, annotations.get(config.ANNOTATION_STRATEGY, 'default'))
    
    logging.info(f"POD [{pod_name}] - Strategy applied: [{strategy}]")

    # Filtro Hardware
    candidate_nodes = dict(nodes_dict)
    required_hw = {t.strip().lower() for t in annotations.get(config.ANNOTATION_HW_REQUIRED, '').split(',') if t.strip()}
    if required_hw:
        node_hw = get_node_hw_tags(v1, candidate_nodes)
        candidate_nodes = {n: ip for n, ip in candidate_nodes.items() if required_hw.issubset(node_hw.get(n, set()))}
        if not candidate_nodes:
            logging.error(f"No node matches hw constraints {required_hw}. Pod stays Pending.")
            return None

    # Fetch Risorse K8s
    resource_pct = get_resource_usage_percent(v1, candidate_nodes)
    
    # Filtro Sicurezza
    if resource_pct:
        safe_nodes = {
            n: ip for n, ip in candidate_nodes.items() 
            if resource_pct.get(n, {}).get('cpu_pct', 0) < config.MAX_CPU_USAGE_PERCENT 
            and resource_pct.get(n, {}).get('mem_pct', 0) < config.MAX_MEM_USAGE_PERCENT
        }
        if safe_nodes: 
            candidate_nodes = safe_nodes

    w_strat, w_cpu, w_mem = config.WEIGHT_STRATEGY, config.WEIGHT_CPU, config.WEIGHT_MEM
    strategy_metrics = None

    if strategy == 'minimize-cpu-load':
        logging.warning("RCA Override Active: Maximizing CPU and RAM priority, ignoring latency.")
        w_strat, w_cpu, w_mem = 0.0, 0.5, 0.5
    elif strategy == 'minimize-latency':
        target = annotations.get(config.ANNOTATION_LATENCY_TARGET, '').replace('\\', '\\\\').replace('"', '\\"')
        query = f'avg(probe_duration_seconds{{instance="{target}"}}) by (kubernetes_node)' if target else 'avg(probe_duration_seconds) by (kubernetes_node)'
        strategy_metrics = get_prometheus_metric(query)
    elif strategy == 'temperature-aware':
        strategy_metrics = get_prometheus_metric('avg(node_hwmon_temp_celsius) by (instance)')
    elif strategy == 'disk-io-aware':
        strategy_metrics = get_prometheus_metric('sum(rate(node_disk_io_time_seconds_total{device=~"sd.*|vd.*|nvme.*|mmcblk.*"}[2m])) by (instance)')

    cpu_raw = {n: resource_pct.get(n, {}).get('cpu_pct', 0) for n in candidate_nodes if n in resource_pct}
    mem_raw = {n: resource_pct.get(n, {}).get('mem_pct', 0) for n in candidate_nodes if n in resource_pct}
    
    norm_strat = {}
    if strategy_metrics:
        raw_strat = {n: strategy_metrics.get(n, strategy_metrics.get(ip)) for n, ip in candidate_nodes.items() if strategy_metrics.get(n, strategy_metrics.get(ip)) is not None}
        norm_strat = _normalize(raw_strat)
        
    norm_cpu = _normalize(cpu_raw) if cpu_raw else {}
    norm_mem = _normalize(mem_raw) if mem_raw else {}

    total_w = w_strat + w_cpu + w_mem
    if total_w == 0: 
        logging.warning("No metrics available for scoring. Using Round-Robin fallback.")
        return _get_round_robin_node(candidate_nodes)

    scores = {}
    for n in candidate_nodes:
        if (w_strat > 0 and n not in norm_strat) or (w_cpu > 0 and n not in norm_cpu) or (w_mem > 0 and n not in norm_mem):
            scores[n] = 999.0
            continue
        scores[n] = ((norm_strat.get(n, 1.0) * w_strat) + 
                     (norm_cpu.get(n, 1.0) * w_cpu) + 
                     (norm_mem.get(n, 1.0) * w_mem)) / total_w

    if all(s == 999.0 for s in scores.values()):
        logging.warning("Total metric failure across all valid nodes. Using Round-Robin fallback.")
        return _get_round_robin_node(candidate_nodes)

    best_node = min(scores, key=scores.get)
    
    with config.shared_lock:
        if pod_key in config.SHARED_OVERRIDES:
            del config.SHARED_OVERRIDES[pod_key]

    return best_node