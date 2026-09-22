import logging
import datetime
from kubernetes import client

def _parse_cpu_to_millicores(cpu_str):
    if not cpu_str: return None
    cpu_str = str(cpu_str)
    if cpu_str.endswith('n'): return float(cpu_str[:-1]) / 1_000_000.0
    if cpu_str.endswith('u'): return float(cpu_str[:-1]) / 1_000.0
    if cpu_str.endswith('m'): return float(cpu_str[:-1])
    try: return float(cpu_str) * 1000.0
    except ValueError: return None

def _parse_memory_to_ki(mem_str):
    if not mem_str: return None
    mem_str = str(mem_str)
    units = {'Ki': 1, 'Mi': 1024, 'Gi': 1024 ** 2}
    for suffix, multiplier in units.items():
        if mem_str.endswith(suffix): return float(mem_str[:-len(suffix)]) * multiplier
    try: return float(mem_str) / 1024.0
    except ValueError: return None

def get_available_nodes(v1):
    nodes = v1.list_node()
    valid_nodes = {}
    for n in nodes.items:
        is_ready = any(c.type == 'Ready' and c.status == 'True' for c in (n.status.conditions or []))
        is_schedulable = not any(t.effect == 'NoSchedule' for t in (n.spec.taints or []))
        if is_ready and is_schedulable:
            ip = next((a.address for a in (n.status.addresses or []) if a.type == 'InternalIP'), None)
            if ip: valid_nodes[n.metadata.name] = ip
    return valid_nodes

def get_node_hw_tags(v1, nodes_dict):
    tags = {}
    try:
        nodes = v1.list_node()
        for n in nodes.items:
            name = n.metadata.name
            if name in nodes_dict:
                raw = (n.metadata.annotations or {}).get('iot-scheduler/hw-tags', '')
                tags[name] = {t.strip().lower() for t in raw.split(',') if t.strip()}
    except Exception:
        pass
    return tags

def get_resource_usage_percent(v1, nodes_dict):
    try:
        custom_api = client.CustomObjectsApi()
        metrics = custom_api.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
        usage = {}
        for item in metrics.get('items', []):
            name = item['metadata']['name']
            if name in nodes_dict:
                cpu = _parse_cpu_to_millicores(item['usage'].get('cpu'))
                mem = _parse_memory_to_ki(item['usage'].get('memory'))
                if cpu and mem: usage[name] = {'cpu': cpu, 'mem': mem}
        
        nodes = v1.list_node()
        capacity = {}
        for n in nodes.items:
            if n.metadata.name in usage:
                cpu = _parse_cpu_to_millicores(n.status.allocatable.get('cpu'))
                mem = _parse_memory_to_ki(n.status.allocatable.get('memory'))
                if cpu and mem: capacity[n.metadata.name] = {'cpu': cpu, 'mem': mem}

        pct = {}
        for n in capacity:
            pct[n] = {
                'cpu_pct': (usage[n]['cpu'] / capacity[n]['cpu']) * 100,
                'mem_pct': (usage[n]['mem'] / capacity[n]['mem']) * 100
            }
        return pct
    except Exception as e:
        logging.warning(f"Metrics Server error: {e}")
        return {}

def delete_pod(v1, namespace, pod_name):
    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        logging.info(f"POD {namespace}/{pod_name} eliminated (RCA trigger).")
        return True
    except Exception as e:
        logging.error(f"Failed to delete POD {pod_name}: {e}")
        return False

def emit_warning_event(v1, pod_name, namespace, uid, reason, message):
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        event = client.CoreV1Event(
            metadata=client.V1ObjectMeta(
                generate_name=f"{pod_name}-entanglement-",
                namespace=namespace,
            ),
            involved_object=client.V1ObjectReference(
                api_version="v1", kind="Pod",
                name=pod_name, namespace=namespace, uid=uid,
            ),
            reason=reason,
            message=message,
            type="Warning",
            source=client.V1EventSource(component="entanglement-watchdog"),
            first_timestamp=now,
            last_timestamp=now,
            count=1,
        )
        v1.create_namespaced_event(namespace=namespace, body=event)
    except Exception as e:
        logging.warning(f"Failed to emit Event for {pod_name}: {e}")