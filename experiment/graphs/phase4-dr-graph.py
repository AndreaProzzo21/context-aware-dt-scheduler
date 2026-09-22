"""
=============================================================================
 IoT-Twin-Scheduler: Phase 4 Disaster Recovery Graph Generator
=============================================================================
"""

import requests
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import datetime
import time
from kubernetes import client, config

plt.rcParams.update({
    'font.family': 'serif', 'font.size': 12, 'axes.labelsize': 14,
    'axes.titlesize': 14, 'axes.titleweight': 'bold', 'xtick.labelsize': 12,
    'ytick.labelsize': 12, 'legend.fontsize': 12, 'figure.autolayout': True,
    'axes.grid': True, 'grid.alpha': 0.6, 'grid.linestyle': ':', 'grid.color': '#999999'
})

PROMETHEUS_URL = "http://127.0.0.1:9090"
WINDOW_SECONDS = 720 
STEP_SECONDS = 5

def get_prom_data(query, start, end, step):
    params = {'query': query, 'start': start, 'end': end, 'step': step}
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range", params=params)
        response.raise_for_status()
        return response.json().get('data', {}).get('result', [])
    except Exception as e:
        print(f"[-] Errore Prometheus: {e}")
        return []

def get_raw_node(metric_dict):
    return metric_dict.get('kubernetes_node', metric_dict.get('node', metric_dict.get('instance', 'Unknown')))

def clean_node_name(raw_name):
    """Traduce sia gli hostname che gli IP nei nomi accademici Node A, B, C"""
    if not raw_name or raw_name == "Unknown": return "Unknown"
    raw = raw_name.split(':')[0].lower()
    
    # Mapping per Hostname
    if "worker-1" in raw: return "Node A"
    if "worker-2" in raw: return "Node B"
    if "worker-4" in raw or "worker-3" in raw: return "Node C"
    
    # Mapping per Indirizzo IP (Il problema che hai notato)
    if "192.168.0.62" in raw: return "Node A"
    if "192.168.0.63" in raw: return "Node B"
    if "192.168.0.64" in raw or "192.168.0.65" in raw: return "Node C"
    
    return raw_name.split(':')[0]

def plot_cpu_migration(results, filename):
    if not results: return
    fig, ax = plt.subplots(figsize=(10, 5))
    line_styles = ['-', '--', '-.']
    colors = ['#1f77b4', '#d62728', '#2ca02c'] 
    results_sorted = sorted(results, key=lambda x: clean_node_name(get_raw_node(x['metric'])))
    plotted_lines = 0
    for res in results_sorted:
        nodo = clean_node_name(get_raw_node(res['metric']))
        raw_vals = str(res['metric'].values()).lower()
        if nodo == "Unknown" or "192.168.0.61" in raw_vals or "controlplane" in nodo.lower() or "localhost" in nodo.lower(): 
            continue
        times = [datetime.datetime.fromtimestamp(float(v[0])) for v in res['values']]
        values = [float(v[1]) for v in res['values']]
        if not values: continue
        ax.plot(times, values, label=nodo, linestyle=line_styles[plotted_lines % len(line_styles)], color=colors[plotted_lines % len(colors)], linewidth=2.0)
        plotted_lines += 1

    ax.set_ylabel('CPU Utilization (%)')
    ax.set_xlabel('Time')
    ax.set_title('Workload Migration & Disaster Recovery Telemetry')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    fig.autofmt_xdate()
    ax.set_ylim(0, max([max([float(v[1]) for v in res['values']]) for res in results if 'values' in res] + [10]) * 1.2)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax.legend(loc='upper right', framealpha=0.9, edgecolor='black')
    plt.savefig(filename, dpi=300)
    print(f"[+] Salvato: {filename}")
    plt.close()

def plot_dr_pod_status(node_counts, title, filename):
    nodes = list(node_counts.keys())
    values = list(node_counts.values())
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ['#d32f2f' if n == 'Pending\n(Fail-Safe)' else '#a0a0a0' for n in nodes]
    bars = ax.bar(nodes, values, color=colors, edgecolor='black', width=0.5, zorder=3)
    ax.set_ylabel('Number of Scheduled Pods')
    ax.set_title(title)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    for i, v in enumerate(values): ax.text(i, v + 0.1, str(int(v)), ha='center', va='bottom', fontweight='bold')
    ax.set_ylim(0, max(max(values) * 1.3, 1.5)) 
    plt.savefig(filename, dpi=300)
    print(f"[+] Salvato: {filename}")
    plt.close()

if __name__ == "__main__":
    print("[*] Estrazione Dati per Phase 4 (Disaster Recovery)...")
    end_time = int(time.time())
    start_time = end_time - WINDOW_SECONDS
    
    query_cpu = '100 - (avg by (node, kubernetes_node, instance) (irate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)'
    range_cpu = get_prom_data(query_cpu, start_time, end_time, STEP_SECONDS)
    plot_cpu_migration(range_cpu, 'fig_10_phase4_cpu_migration.png')

    print("[*] Interrogazione K8s API per stato Pod (Fail-Safe vs Fail-Deadly)...")
    try:
        try: config.load_kube_config()
        except: config.load_incluster_config()
        v1 = client.CoreV1Api()
        pods = v1.list_pod_for_all_namespaces(watch=False)
        
        default_counts = {"Node A": 0, "Node B\n(Offline)": 0, "Node C": 0, "Pending\n(Fail-Safe)": 0}
        custom_counts = {"Node A": 0, "Node B\n(Offline)": 0, "Node C": 0, "Pending\n(Fail-Safe)": 0}

        for p in pods.items:
            pod_name = p.metadata.name
            if "dt-hw-dr-default" in pod_name or "dt-hw-dr-custom" in pod_name:
                target_dict = default_counts if "default" in pod_name else custom_counts
                if p.status.phase == "Pending":
                    target_dict["Pending\n(Fail-Safe)"] += 1
                else:
                    n_clean = clean_node_name(p.spec.node_name)
                    if n_clean == "Node B": target_dict["Node B\n(Offline)"] += 1
                    elif n_clean in target_dict: target_dict[n_clean] += 1

        plot_dr_pod_status(default_counts, 'Default Scheduler: Fail-Deadly (Wrong Hardware)', 'fig_11a_phase4_hw_dr_default.png')
        plot_dr_pod_status(custom_counts, 'Custom IoT-Twin Scheduler: Fail-Safe (Pending)', 'fig_11b_phase4_hw_dr_custom.png')
    except Exception as e: print(f"[-] Errore Kubernetes API: {e}")
    print("[✔] Script Phase 4 completato con successo!")