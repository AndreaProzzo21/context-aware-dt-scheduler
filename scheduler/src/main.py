import threading
import time
import logging
import signal
from kubernetes import client, config as k8s_config, watch

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import config.config as config
from core.scheduler_engine import calculate_best_node
from utils.kubernetes_utils import get_available_nodes
from core.watchdog_thread import watchdog_loop

def handle_shutdown(signum, frame):
    logging.info(f"Received signal {signum}. Shutting down gracefully...")
    config.shutdown_requested = True

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

def _verify_bind_result(api_instance, pod_name, namespace, node_name, retries=3, delay=1.0):
    for attempt in range(1, retries + 1):
        try:
            pod = api_instance.read_namespaced_pod(name=pod_name, namespace=namespace)
            if pod.spec.node_name == node_name:
                logging.info(f"Verified: POD [{pod_name}] is actively bound to [{node_name}]")
                return True
        except Exception:
            pass
        time.sleep(delay)
    logging.error(f"Verification failed for POD [{pod_name}].")
    return False

def bind_pod(v1, pod_name, namespace, node_name):
    target = client.V1ObjectReference(api_version='v1', kind='Node', name=node_name)
    meta = client.V1ObjectMeta(name=pod_name, namespace=namespace)
    binding = client.V1Binding(api_version='v1', kind='Binding', target=target, metadata=meta)
    
    try:
        v1.create_namespaced_pod_binding(name=pod_name, namespace=namespace, body=binding)
        logging.info(f"POD [{pod_name}] successfully bound to [{node_name}]")
        
    except ValueError as ve:
        if "Invalid value for `target`, must not be `None`" in str(ve):
            logging.info(f"POD [{pod_name}] bind successful (bypassed Python K8s client response bug)")
            _verify_bind_result(v1, pod_name, namespace, node_name)
        else:
            logging.error(f"Unexpected value error during bind: {ve}")
    except Exception as e:
        logging.error(f"Bind API error: {e}")

def main():
    try: 
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException: 
        k8s_config.load_kube_config()

    v1 = client.CoreV1Api()
    
    wt = threading.Thread(target=watchdog_loop, args=(v1,), daemon=True)
    wt.start()

    logging.info("Main Orchestrator Loop started...")
    while not config.shutdown_requested:
        w = watch.Watch()
        try:
            for event in w.stream(v1.list_pod_for_all_namespaces, timeout_seconds=config.WATCH_STREAM_TIMEOUT_SECONDS):
                if config.shutdown_requested: 
                    break
                
                if event['type'] in ('ADDED', 'MODIFIED'):
                    pod = event['object']
                    
                    if pod.status.phase == 'Pending' and pod.spec.scheduler_name == config.SCHEDULER_NAME:
                        if pod.spec.node_name:
                            continue
                            
                        nodes = get_available_nodes(v1)
                        if nodes:
                            best = calculate_best_node(v1, nodes, pod.metadata.name, pod.metadata.namespace, pod.metadata.annotations or {})
                            if best:
                                logging.info(f"Winning node for {pod.metadata.name} is [{best}]")
                                bind_pod(v1, pod.metadata.name, pod.metadata.namespace, best)
        except Exception as e:
            if not config.shutdown_requested:
                logging.error(f"Watch error: {e}", exc_info=True) 
                time.sleep(config.WATCH_ERROR_BACKOFF_SECONDS)
        finally:
            w.stop()
            
    logging.info("Scheduler terminated cleanly.")

if __name__ == '__main__':
    main()