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
NAMESPACE = os.getenv("NAMESPACE", "default")
MINUTES_AGO = int(os.getenv("MINUTES_AGO", "10"))
THRESHOLD = float(os.getenv("THRESHOLD_MS", "450"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/app/output")

POD_CUSTOM = "twin-machine-custom-0"
POD_DEFAULT = "twin-machine-default-0"

def fetch_prometheus_data(query, start_time, end_time, step="1s"):
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
            values = res['values']
            df_temp = pd.DataFrame(values, columns=['timestamp', 'value'])
            df_temp['timestamp'] = pd.to_datetime(df_temp['timestamp'], unit='s')
            df_temp['value'] = df_temp['value'].astype(float)
            df_temp.set_index('timestamp', inplace=True)
            df_list.append(df_temp)
            
        return pd.concat(df_list, axis=1).max(axis=1).to_frame(name='value')
    
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

def plot_empty_fallback(ax, title):
    ax.text(0.5, 0.5, 'NO DATA AVAILABLE', 
            horizontalalignment='center', verticalalignment='center', 
            fontsize=14, color='black', transform=ax.transAxes, fontweight='bold')
    setup_plot_style(ax, title, 'Value')

def generate_entanglement_breakdown(pod_name, start_time, end_time, suffix_name, title_prefix):
    """Genera il grafico ad area bianco/nero per il breakdown dell'entanglement di uno specifico pod."""
    logging.info(f"Generazione Entanglement Breakdown per {pod_name}...")
    
    q_pt = f'max(pt_dt_delay{{pod="{pod_name}", namespace="{NAMESPACE}"}})'
    q_comp = f'max(dt_comp_delay{{pod="{pod_name}", namespace="{NAMESPACE}"}})'
    q_ent = f'max(entanglement{{pod="{pod_name}", namespace="{NAMESPACE}"}})'
    
    df_pt = fetch_prometheus_data(q_pt, start_time, end_time)
    df_comp = fetch_prometheus_data(q_comp, start_time, end_time)
    df_ent = fetch_prometheus_data(q_ent, start_time, end_time)
    
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    
    if df_ent.empty or df_pt.empty or df_comp.empty:
        plot_empty_fallback(ax, f'{title_prefix} Entanglement Components')
        df_return = pd.DataFrame()
    else:
        df_combined = pd.concat([
            df_pt.iloc[:,0].rename('Network'), 
            df_comp.iloc[:,0].rename('Compute'), 
            df_ent.iloc[:,0].rename('Total')
        ], axis=1)
        
        full_idx = pd.date_range(start=df_combined.index.min(), end=df_combined.index.max(), freq='1S')
        df_combined = df_combined.reindex(full_idx)
        
        ax.fill_between(df_combined.index, 0, df_combined['Network'], 
                        label='Network Delay', facecolor='#f4f4f4', edgecolor='black', hatch='///')
        ax.fill_between(df_combined.index, df_combined['Network'], df_combined['Network'] + df_combined['Compute'], 
                        label='Compute Delay', facecolor='#ffffff', edgecolor='black', hatch='\\\\\\')
        
        ax.plot(df_combined.index, df_combined['Total'], color='black', linewidth=2.5, label='Total Entanglement')
        ax.axhline(y=THRESHOLD, color='black', linestyle='--', linewidth=2, label=f'Threshold ({int(THRESHOLD)}ms)')
        
        setup_plot_style(ax, f'{title_prefix} Entanglement Breakdown', 'Delay (ms)')
        ax.legend(loc='upper left', frameon=True, framealpha=1.0, edgecolor='black', fancybox=False)
        df_return = df_combined[['Total']]

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, f"1_entanglement_breakdown_{suffix_name}.png"))
    plt.close()
    
    return df_return

def generate_sla_chart(df_custom, df_default):
    """Genera il grafico a barre SLA calcolando la percentuale reale dai dataframe di Prometheus."""
    logging.info("Generazione grafico SLA (System Availability)...")
    
    # Se mancano i dati, si usano dei placeholder per evitare crash
    if df_custom.empty:
        custom_healthy_pct, custom_degraded_pct = 0, 100
    else:
        custom_healthy_pct = (df_custom['Total'] <= THRESHOLD).mean() * 100
        custom_degraded_pct = 100 - custom_healthy_pct

    if df_default.empty:
        default_healthy_pct, default_degraded_pct = 0, 100
    else:
        default_healthy_pct = (df_default['Total'] <= THRESHOLD).mean() * 100
        default_degraded_pct = 100 - default_healthy_pct

    labels = ['Default K8s Scheduler', 'IoT-Twin-Scheduler']
    healthy_pcts = [default_healthy_pct, custom_healthy_pct]
    degraded_pcts = [default_degraded_pct, custom_degraded_pct]

    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    width = 0.5
    
    p1 = ax.bar(labels, healthy_pcts, width, label='Entangled (Healthy SLA)', color='#2ca02c', edgecolor='black')
    p2 = ax.bar(labels, degraded_pcts, width, bottom=healthy_pcts, label='Degraded / Synchronization Lost', color='#d62728', edgecolor='black')

    ax.set_ylabel('System Availability (%)', fontsize=12, color='black')
    ax.set_title(f'Cumulative Cyber-Physical Synchronization ({MINUTES_AGO}-Min Window)', fontsize=14, fontweight='bold', pad=15)
    ax.set_ylim(0, 100)
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    ax.set_facecolor('#ffffff')
    ax.legend(loc='lower center', bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False, fontsize=11)

    for idx, rect in enumerate(p1):
        height = rect.get_height()
        if height > 2:
            ax.text(rect.get_x() + rect.get_width()/2., height/2., f'{healthy_pcts[idx]:.1f}%', ha='center', va='center', color='white', fontweight='bold')

    for idx, rect in enumerate(p2):
        height = rect.get_height()
        bottom = rect.get_y()
        if height > 5: 
            ax.text(rect.get_x() + rect.get_width()/2., bottom + height/2., f'{degraded_pcts[idx]:.1f}%', ha='center', va='center', color='white', fontweight='bold')

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "6_empirical_system_availability.png"), bbox_inches='tight')
    plt.close()

def main():
    logging.info(f"Avvio estrazione metriche ({MINUTES_AGO}m) dal server {PROMETHEUS_URL}...")
    end_time = datetime.utcnow().timestamp()
    start_time = end_time - (MINUTES_AGO * 60)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.style.use('seaborn-v0_8-white')

    # 1. Genera Breakdown per Scheduler Custom
    df_tot_custom = generate_entanglement_breakdown(POD_CUSTOM, start_time, end_time, "custom", "IoT-Twin-Scheduler")
    
    # 2. Genera Breakdown per Scheduler Default
    df_tot_default = generate_entanglement_breakdown(POD_DEFAULT, start_time, end_time, "default", "Default K8s Scheduler")

    # 3. Genera Grafico SLA basato sui due dataframe appena estratti
    generate_sla_chart(df_tot_custom, df_tot_default)
    
    logging.info(f"Tutti i grafici sono stati salvati in {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()