import matplotlib.pyplot as plt
import numpy as np

# Dati in minuti
labels = ['Default K8s Scheduler', 'IoT-Twin-Scheduler']
healthy_time = [10, 58]
degraded_time = [50, 2]

# Conversione in percentuali
total_time = 60
healthy_pct = [h / total_time * 100 for h in healthy_time]
degraded_pct = [d / total_time * 100 for d in degraded_time]

width = 0.5
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)

# Creazione delle barre impilate (Tonalità adatte alla stampa)
p1 = ax.bar(labels, healthy_pct, width, label='Entangled (Healthy SLA)', color='#2ca02c', edgecolor='black')
p2 = ax.bar(labels, degraded_pct, width, bottom=healthy_pct, label='Degraded / Synchronization Lost', color='#d62728', edgecolor='black')

# Formattazione
ax.set_ylabel('System Availability (%)', fontsize=12)
ax.set_title('Cumulative Cyber-Physical Synchronization (1-Hour Window)', fontsize=14, fontweight='bold', pad=15)
ax.set_ylim(0, 100)
ax.grid(axis='y', linestyle='--', alpha=0.7)
ax.legend(loc='lower center', bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False, fontsize=11)

# Aggiunta delle etichette con i valori percentuali esatti sulle barre
for idx, rect in enumerate(p1):
    height = rect.get_height()
    ax.text(rect.get_x() + rect.get_width()/2., height/2., f'{healthy_pct[idx]:.1f}%', ha='center', va='center', color='white', fontweight='bold')

for idx, rect in enumerate(p2):
    height = rect.get_height()
    bottom = rect.get_y()
    # Posiziona l'etichetta al centro della porzione rossa
    if height > 5: # Evita sovrapposizioni se la barra è troppo piccola
        ax.text(rect.get_x() + rect.get_width()/2., bottom + height/2., f'{degraded_pct[idx]:.1f}%', ha='center', va='center', color='white', fontweight='bold')

plt.tight_layout()
plt.savefig('system_availability_comparison.png', bbox_inches='tight')
plt.show()