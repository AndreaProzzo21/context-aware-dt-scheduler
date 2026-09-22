import requests
import logging
import config.config as config

def get_prometheus_metric(query):
    try:
        response = requests.get(
            f"{config.PROMETHEUS_URL}/api/v1/query",
            params={'query': query},
            timeout=config.PROMETHEUS_TIMEOUT
        )
        response.raise_for_status()
        results = response.json().get('data', {}).get('result', [])

        node_metrics = {}
        for res in results:
            labels = res.get('metric', {})
            raw_target = labels.get('kubernetes_node') or labels.get('instance', '')
            if raw_target:
                clean_target = raw_target.split(':')[0]
                node_metrics[clean_target] = float(res['value'][1])
        return node_metrics
    except Exception as e:
        logging.warning(f"Prometheus fetch failed for query: {e}")
        return None

def get_twin_metrics(pod_name, namespace):
    """Recupera le tre metriche per l'RCA (Root Cause Analysis)."""
    metrics = {}
    for m in ['entanglement', 'pt_dt_delay', 'dt_comp_delay']:
        query = f'avg({m}{{pod="{pod_name}", namespace="{namespace}"}})'
        try:
            res = requests.get(
                f"{config.PROMETHEUS_URL}/api/v1/query", 
                params={'query': query}, 
                timeout=config.PROMETHEUS_TIMEOUT
            )
            res.raise_for_status()
            data = res.json().get('data', {}).get('result', [])
            if data:
                metrics[m] = float(data[0]['value'][1])
        except Exception:
            pass
    return metrics