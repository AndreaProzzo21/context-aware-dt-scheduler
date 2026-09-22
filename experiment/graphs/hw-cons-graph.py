"""
=============================================================================
 IoT-Twin-Scheduler: Phase 2 Hardware-Aware Comparison Graph Generator
=============================================================================
 Genera due grafici distinti per la comparazione hardware:
 - fig_06a_hardware_default.png (Default K8s Scheduler)
 - fig_06b_hardware_custom.png (Custom IoT-Twin Scheduler)
"""

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
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
    'figure.autolayout': True,
    'axes.grid': True,
    'grid.alpha': 0.6,
    'grid.linestyle': ':',
    'grid.color': '#999999'
})

def clean_node_name(raw_name):
    """Pulisce il nome del nodo e lo mappa nel formato accademico (Node A, B, C)."""
    if not raw_name:
        return "Unknown"
    clean = raw_name.split(':')[0].replace('talos-tim-', '').capitalize()
    
    # Mappatura Worker -> Node
    if clean == "Worker-1":
        return "Node A"
    elif clean == "Worker-2":
        return "Node B"
    elif clean == "Worker-3":
        return "Node C"
        
    return clean

def plot_hardware_pod_distribution(node_counts, title, filename):
    if not node_counts:
        print(f"[-] Nessun dato da plotare per {filename}.")
        return
        
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
        
    max_val = max(values) if values else 1
    ax.set_ylim(0, max(max_val * 1.3, 1.5)) 
    
    plt.savefig(filename, dpi=300)
    print(f"[+] Grafico salvato con successo come: {filename}")
    plt.close()

if __name__ == "__main__":
    print("[*] Estrazione dati per Hardware-Aware Comparison (Phase 2)...")
    try:
        try:
            config.load_kube_config()
        except Exception:
            config.load_incluster_config()
            
        v1 = client.CoreV1Api()
        pods = v1.list_pod_for_all_namespaces(watch=False)
        
        default_counts = {"Node A": 0, "Node B": 0, "Node C": 0}
        custom_counts = {"Node A": 0, "Node B": 0, "Node C": 0}
        
        default_found = 0
        custom_found = 0

        for p in pods.items:
            pod_name = p.metadata.name
            node_name = p.spec.node_name
            
            if not node_name:
                continue
                
            n_clean = clean_node_name(node_name)
            if "192.168.0.61" in node_name or "controlplane" in n_clean.lower():
                continue

            # Mappatura basata sui prefissi dei due deployment nel file unificato
            if "dt-hardware-default" in pod_name:
                if n_clean not in default_counts: default_counts[n_clean] = 0
                default_counts[n_clean] += 1
                default_found += 1
                
            elif "dt-hardware-custom" in pod_name:
                if n_clean not in custom_counts: custom_counts[n_clean] = 0
                custom_counts[n_clean] += 1
                custom_found += 1
                        
        print(f"[+] Trovati {default_found} pod default e {custom_found} pod custom.")
        
        plot_hardware_pod_distribution(
            default_counts, 
            'Default K8s Scheduler (Hardware-Blind)', 
            'fig_06a_hardware_default.png'
        )
        
        plot_hardware_pod_distribution(
            custom_counts, 
            'Custom IoT-Twin Scheduler (Hardware-Aware)', 
            'fig_06b_hardware_custom.png'
        )
        
    except Exception as e:
        print(f"[-] Errore durante l'interrogazione dell'API di Kubernetes: {e}")

    print("[✔] Script completato.")