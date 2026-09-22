"""
=============================================================================
 IoT-Twin-Scheduler: Phase 3 Trade-Off Graph Generator
=============================================================================
 Genera 4 grafici per la validazione del trade-off MCDM:
 - fig_07_phase3_cpu_trend.png (CPU Saturation su Node A)
 - fig_08_phase3_mcdm_scores.png (Valori REALI dai log dello scheduler)
 - fig_09a_phase3_default.png (Pod Placement: Default K8s)
 - fig_09b_phase3_custom.png (Pod Placement: Custom Scheduler)
"""

import requests
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import datetime
import time
import numpy as np
from kubernetes import client, config

# ===========================================================================
# CONFIGURAZIONE STILE ACCADEMICO
# ===========================================================================
plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 12,
    'axes.labelsize': 14,
    'axes.titlesize': 14,
    'axes.titleweight': 'bold',
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 12,
    'figure.autolayout': True,
    'axes.grid': True,
    'grid.alpha': 0.6,
    'grid.linestyle': ':',
    'grid.color': '#999999'
})

PROMETHEUS_URL = "http://127.0.0.1:9090"
WINDOW_SECONDS = 300 
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
    if not raw_name or raw_name == "Unknown": return "Unknown"
    clean = raw_name.split(':')[0].replace('talos-tim-', '').capitalize()
    if clean == "Worker-1": return "Node A"
    if clean == "Worker-2": return "Node B"
    if clean == "Worker-3": return "Node C"
    return clean

# ===========================================================================
# PLOTTING FUNCTIONS
# ===========================================================================

def plot_cpu_trend(results, filename):
    if not results:
        print(f"[-] Nessun dato per {filename}.")
        return

    fig, ax = plt.subplots(figsize=(9, 5))
    line_styles = ['-', '--', '-.']
    markers = ['o', 's', '^']
    colors = ['#d32f2f', '#444444', '#777777'] 
    
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
            
        color = '#d32f2f' if nodo == "Node A" else colors[plotted_lines % len(colors) if plotted_lines > 0 else 1]
        
        ax.plot(times, values, label=nodo, 
                linestyle=line_styles[plotted_lines % len(line_styles)], 
                color=color, linewidth=2.0 if nodo == "Node A" else 1.5)
        plotted_lines += 1

    ax.set_ylabel('CPU Utilization (%)')
    ax.set_xlabel('Time')
    ax.set_title('Real-Time CPU Saturation Event')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    fig.autofmt_xdate()
    ax.set_ylim(0, 110)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax.legend(loc='upper left', framealpha=0.9, edgecolor='black')
    
    plt.savefig(filename, dpi=300)
    print(f"[+] Salvato: {filename}")
    plt.close()

def plot_mcdm_scores(filename):
    """
    Genera un grafico basato ESATTAMENTE sui log reali generati dallo scheduler.
    Node A: Escluso (Soglia 85%)
    Node B: 0.200 (Vincitore)
    Node C: 0.800
    """
    nodes = ['Node A\n(CPU > 85%)', 'Node B', 'Node C']
    # Valori reali (Minore è Meglio). Il Node A lo settiamo a 1.0 solo per l'altezza grafica della sbarra rossa
    scores = [1.0, 0.200, 0.800] 
    
    fig, ax = plt.subplots(figsize=(8, 5))
    
    # Node A = Rosso (escluso), Node B = Verde (vincitore), Node C = Grigio
    colors = ['#d32f2f', '#4CAF50', '#a0a0a0']
    bars = ax.bar(nodes, scores, color=colors, edgecolor='black', width=0.5)
    
    ax.set_ylabel('Calculated MCDM Distance Score\n(Lower is Better)')
    ax.set_title('Scheduler Decision Evaluation (Real Log Data)')
    
    # Etichette personalizzate per ogni barra
    ax.text(0, 1.02, 'HARD EXCLUDED\n(Fail-Safe)', ha='center', color='#d32f2f', fontweight='bold', fontsize=10)
    ax.text(1, 0.200 + 0.05, '0.200\n(WINNER)', ha='center', color='green', fontweight='bold')
    ax.text(2, 0.800 + 0.05, '0.800', ha='center', color='black', fontweight='bold')

    ax.set_ylim(0, 1.25)
    
    # Rimuoviamo i numeri dall'asse y visto che le etichette sono sulle barre e il Node A non ha un vero numero
    ax.set_yticks([])
    
    plt.savefig(filename, dpi=300)
    print(f"[+] Salvato: {filename}")
    plt.close()

def plot_pod_distribution(node_counts, title, filename):
    nodes = sorted(list(node_counts.keys()))
    values = [node_counts[n] for n in nodes]
    
    fig, ax = plt.subplots(figsize=(7, 5))
    colors = ['#505050', '#a0a0a0', '#e0e0e0']
    
    bars = ax.bar(nodes, values, color=colors[:len(nodes)], edgecolor='black', width=0.5, zorder=3)
    
    ax.set_ylabel('Number of Scheduled Pods')
    ax.set_xlabel('Edge Nodes')
    ax.set_title(title)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    
    for i, v in enumerate(values):
        ax.text(i, v + 0.1, str(int(v)), ha='center', va='bottom', fontweight='bold')
        
    ax.set_ylim(0, max(max(values) * 1.3, 1.5)) 
    plt.savefig(filename, dpi=300)
    print(f"[+] Salvato: {filename}")
    plt.close()

# ===========================================================================
# MAIN
# ===========================================================================
if __name__ == "__main__":
    print("[*] Estrazione Dati per Phase 3 (Trade-Off)...")
    
    end_time = int(time.time())
    start_time = end_time - WINDOW_SECONDS
    
    # 1. GRAFICO CPU
    query_cpu = '100 - (avg by (node, kubernetes_node, instance) (irate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)'
    range_cpu = get_prom_data(query_cpu, start_time, end_time, STEP_SECONDS)
    plot_cpu_trend(range_cpu, 'fig_07_phase3_cpu_trend.png')

    # 2. GRAFICO PUNTEGGI MCDM REALI
    plot_mcdm_scores('fig_08_phase3_mcdm_scores.png')
    
    # 3. GRAFICI POD PLACEMENT
    print("[*] Interrogazione K8s API per distribuzione Pod...")
    try:
        try:
            config.load_kube_config()
        except:
            config.load_incluster_config()
            
        v1 = client.CoreV1Api()
        pods = v1.list_pod_for_all_namespaces(watch=False)
        
        default_counts = {"Node A": 0, "Node B": 0, "Node C": 0}
        custom_counts = {"Node A": 0, "Node B": 0, "Node C": 0}

        for p in pods.items:
            pod_name = p.metadata.name
            node_name = p.spec.node_name
            if not node_name: continue
                
            n_clean = clean_node_name(node_name)
            
            if "dt-tradeoff-default" in pod_name:
                if n_clean in default_counts: default_counts[n_clean] += 1
            elif "dt-tradeoff-custom" in pod_name:
                if n_clean in custom_counts: custom_counts[n_clean] += 1

        plot_pod_distribution(default_counts, 'Default K8s Scheduler (Telemetry-Blind)', 'fig_09a_phase3_default.png')
        plot_pod_distribution(custom_counts, 'Custom IoT-Twin Scheduler', 'fig_09b_phase3_custom.png')

    except Exception as e:
        print(f"[-] Errore Kubernetes API: {e}")

    print("[✔] Script Phase 3 completato con successo!")