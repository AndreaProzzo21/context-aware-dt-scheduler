import os
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURAZIONI ---
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
POD_NAME = os.getenv("POD_NAME", "twin-machine-01-0") # Cambialo nel nome corretto del tuo pod
NAMESPACE = os.getenv("NAMESPACE", "default")
MINUTES_AGO = int(os.getenv("MINUTES_AGO", "10"))
THRESHOLD = float(os.getenv("THRESHOLD_MS", "300"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/app/output")

# Stili per le linee (Garantiscono distinguibilità in B/N)
LINE_FORMATS = [
    {'linestyle': '-',  'marker': 'o'},
    {'linestyle': '--', 'marker': 's'},
    {'linestyle': '-.', 'marker': '^'},
    {'linestyle': ':',  'marker': 'd'},
    {'linestyle': '-',  'marker': 'x'}
]

# --- MAPPATURA NODI ---
def get_node_name(instance_str):
    if '61' in instance_str: return 'Control Plane'
    if '62' in instance_str: return 'Node A'
    if '63' in instance_str: return 'Node B'
    if '64' in instance_str: return 'Node C'
    return instance_str

def fetch_prometheus_data(query, start_time, end_time, step="1s", label_key=None):
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={'query': query, 'start': start_time, 'end': end_time, 'step': step}
        )
        response.raise_for_status()
        results = response.json().get('data', {}).get('result', [])
        
        if not results:
            logging.warning(f"Nessun dato trovato per la query: {query}")
            return pd.DataFrame()
        
        df_list = []
        for i, res in enumerate(results):
            if label_key and label_key in res['metric']:
                raw_val = res['metric'][label_key].split(':')[0]
                col_name = get_node_name(raw_val)
            else:
                col_name = f"value_{i}"
                
            values = res['values']
            df_temp = pd.DataFrame(values, columns=['timestamp', col_name])
            df_temp['timestamp'] = pd.to_datetime(df_temp['timestamp'], unit='s')
            df_temp[col_name] = df_temp[col_name].astype(float)
            df_temp.set_index('timestamp', inplace=True)
            df_list.append(df_temp)
            
        return pd.concat(df_list, axis=1)
    
    except Exception as e:
        logging.error(f"Errore query [{query[:30]}...]: {e}")
        return pd.DataFrame()

def setup_plot_style(ax, title, ylabel):
    """Formatta gli assi in stile accademico minimalista (IEEE/APA)."""
    ax.set_title(title, fontsize=14, pad=15, fontweight='bold', color='black')
    ax.set_ylabel(ylabel, fontsize=12, color='black')
    ax.set_xlabel('Time', fontsize=12, color='black')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('black')
    ax.spines['bottom'].set_color('black')
    
    plt.xticks(rotation=45, color='black')
    plt.yticks(color='black')
    ax.grid(True, linestyle=':', color='#cccccc', alpha=0.8)
    ax.set_facecolor('#ffffff')
    ax.legend(loc='best', frameon=True, framealpha=1.0, edgecolor='black', fancybox=False)

def plot_empty_fallback(ax, title):
    ax.text(0.5, 0.5, 'NO DATA AVAILABLE', 
            horizontalalignment='center', verticalalignment='center', 
            fontsize=14, color='black', transform=ax.transAxes, fontweight='bold')
    setup_plot_style(ax, title, 'Value')

def main():
    logging.info(f"Estrazione metriche ({MINUTES_AGO}m) dal server {PROMETHEUS_URL}...")
    end_time = datetime.utcnow().timestamp()
    start_time = end_time - (MINUTES_AGO * 60)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    plt.style.use('seaborn-v0_8-white')

    # ---------------------------------------------------------
    # 1. GRAFICO: Scomposizione Entanglement
    # ---------------------------------------------------------
    logging.info("Generazione Grafico 1: Entanglement Breakdown...")
    # FIX: Uso max() per unire vecchie e nuove istanze del pod in un'unica serie!
    q_pt = f'max(pt_dt_delay{{pod="{POD_NAME}", namespace="{NAMESPACE}"}})'
    q_comp = f'max(dt_comp_delay{{pod="{POD_NAME}", namespace="{NAMESPACE}"}})'
    q_ent = f'max(entanglement{{pod="{POD_NAME}", namespace="{NAMESPACE}"}})'
    
    df_pt = fetch_prometheus_data(q_pt, start_time, end_time)
    df_comp = fetch_prometheus_data(q_comp, start_time, end_time)
    df_ent = fetch_prometheus_data(q_ent, start_time, end_time)
    
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    if df_ent.empty or df_pt.empty or df_comp.empty:
        plot_empty_fallback(ax, 'Digital Twin Entanglement Components')
    else:
        # Allineamento rigoroso per mantenere i buchi (NaN) senza spalmare dati vecchi
        df_combined = pd.concat([
            df_pt.iloc[:,0].rename('Network'), 
            df_comp.iloc[:,0].rename('Compute'), 
            df_ent.iloc[:,0].rename('Total')
        ], axis=1)
        
        # Forza una timeline continua al secondo. I momenti di assenza (pod spento) diventano spazi vuoti nel grafico.
        full_idx = pd.date_range(start=df_combined.index.min(), end=df_combined.index.max(), freq='1S')
        df_combined = df_combined.reindex(full_idx)
        
        ax.fill_between(df_combined.index, 0, df_combined['Network'], 
                        label='Network Delay', facecolor='#f4f4f4', edgecolor='black', hatch='///')
        ax.fill_between(df_combined.index, df_combined['Network'], df_combined['Network'] + df_combined['Compute'], 
                        label='Compute Delay', facecolor='#ffffff', edgecolor='black', hatch='\\\\\\')
        
        ax.plot(df_combined.index, df_combined['Total'], color='black', linewidth=2.5, label='Total Entanglement')
        ax.axhline(y=THRESHOLD, color='black', linestyle='--', linewidth=2, label=f'Threshold ({int(THRESHOLD)}ms)')
        setup_plot_style(ax, 'Digital Twin Entanglement Breakdown and Recovery', 'Delay (ms)')
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "1_entanglement_breakdown.png"))
    plt.close()

    # ---------------------------------------------------------
    # 2. GRAFICO: Network vs Compute
    # ---------------------------------------------------------
    logging.info("Generazione Grafico 2: Delay Components...")
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    if df_pt.empty or df_comp.empty:
        plot_empty_fallback(ax, 'Root Cause Analysis: Delay Components')
    else:
        # Applica lo stesso reindex per il grafico a linee
        df_lines = pd.concat([df_pt.iloc[:,0].rename('Network'), df_comp.iloc[:,0].rename('Compute')], axis=1)
        full_idx_lines = pd.date_range(start=df_lines.index.min(), end=df_lines.index.max(), freq='1S')
        df_lines = df_lines.reindex(full_idx_lines)
        
        mark_spacing = max(1, len(df_lines) // 15)
        
        ax.plot(df_lines.index, df_lines['Network'], label='Network Delay', color='black', 
                linestyle='-', marker='o', markersize=6, markevery=mark_spacing, linewidth=1.5)
        ax.plot(df_lines.index, df_lines['Compute'], label='Compute Delay', color='black', 
                linestyle='--', marker='s', markersize=6, markevery=mark_spacing, linewidth=1.5)
        
        setup_plot_style(ax, 'Root Cause Analysis: Delay Components', 'Delay (ms)')
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "2_delay_components_lines.png"))
    plt.close()

    # ---------------------------------------------------------
    # 3. GRAFICO: Node CPU Usage
    # ---------------------------------------------------------
    logging.info("Generazione Grafico 3: Node CPU...")
    q_cpu = '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'
    df_cpu = fetch_prometheus_data(q_cpu, start_time, end_time, label_key='instance')
    
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    if df_cpu.empty:
        plot_empty_fallback(ax, 'Cluster Nodes CPU Usage')
    else:
        mark_spacing = max(1, len(df_cpu) // 15)
        for i, col in enumerate(df_cpu.columns):
            fmt = LINE_FORMATS[i % len(LINE_FORMATS)]
            ax.plot(df_cpu.index, df_cpu[col], label=col, color='black', 
                    linestyle=fmt['linestyle'], marker=fmt['marker'], markersize=6, 
                    markevery=mark_spacing, linewidth=1.5)
            
        setup_plot_style(ax, 'Cluster Nodes CPU Usage', 'CPU Usage (%)')
        ax.set_ylim([0, 105])
        
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "3_nodes_cpu_usage.png"))
    plt.close()

    # ---------------------------------------------------------
    # 4. GRAFICO: Node RAM Usage
    # ---------------------------------------------------------
    logging.info("Generazione Grafico 4: Node RAM...")
    q_ram = '100 * (1 - ((node_memory_MemAvailable_bytes) / (node_memory_MemTotal_bytes)))'
    df_ram = fetch_prometheus_data(q_ram, start_time, end_time, label_key='instance')
    
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    if df_ram.empty:
        plot_empty_fallback(ax, 'Cluster Nodes Memory Usage')
    else:
        mark_spacing = max(1, len(df_ram) // 15)
        for i, col in enumerate(df_ram.columns):
            fmt = LINE_FORMATS[i % len(LINE_FORMATS)]
            ax.plot(df_ram.index, df_ram[col], label=col, color='black', 
                    linestyle=fmt['linestyle'], marker=fmt['marker'], markersize=6, 
                    markevery=mark_spacing, linewidth=1.5)
            
        setup_plot_style(ax, 'Cluster Nodes Memory Usage', 'Memory Usage (%)')
        ax.set_ylim([0, 105])
        
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "4_nodes_ram_usage.png"))
    plt.close()

    logging.info(f"Grafici salvati in {OUTPUT_DIR}")

if __name__ == "__main__":
    main()