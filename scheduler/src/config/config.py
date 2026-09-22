import os
import threading

# --- KUBERNETES & SYSTEM ---
SCHEDULER_NAME = os.getenv("SCHEDULER_NAME", "iot-twin-scheduler")
WATCH_ERROR_BACKOFF_SECONDS = float(os.getenv("WATCH_ERROR_BACKOFF_SECONDS", "5"))
WATCH_STREAM_TIMEOUT_SECONDS = int(os.getenv("WATCH_STREAM_TIMEOUT_SECONDS", "120"))

# --- PROMETHEUS ---
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-operated.monitoring.svc.cluster.local:9090")
PROMETHEUS_TIMEOUT = float(os.getenv("PROMETHEUS_TIMEOUT_SECONDS", "6"))

# --- RESOURCE SCORING ---
MAX_CPU_USAGE_PERCENT = float(os.getenv("MAX_CPU_USAGE_PERCENT", "85"))
MAX_MEM_USAGE_PERCENT = float(os.getenv("MAX_MEM_USAGE_PERCENT", "85"))
WEIGHT_STRATEGY = float(os.getenv("WEIGHT_STRATEGY", "0.6"))
WEIGHT_CPU = float(os.getenv("WEIGHT_CPU", "0.2"))
WEIGHT_MEM = float(os.getenv("WEIGHT_MEM", "0.2"))

# --- WATCHDOG SETTINGS ---
WATCHDOG_INTERVAL_SECONDS = float(os.getenv("WATCHDOG_INTERVAL_SECONDS", "20"))
SUSTAINED_CHECKS_REQUIRED = int(os.getenv("SUSTAINED_CHECKS_REQUIRED", "3"))
GRACE_PERIOD_SECONDS = float(os.getenv("GRACE_PERIOD_SECONDS", "60"))
COOLDOWN_SECONDS = float(os.getenv("COOLDOWN_SECONDS", "180"))
DEFAULT_ENTANGLEMENT_THRESHOLD_MS = float(os.getenv("DEFAULT_ENTANGLEMENT_THRESHOLD_MS", "300"))

# --- ANNOTATIONS ---
ANNOTATION_STRATEGY = 'iot-scheduler/strategy'
ANNOTATION_LATENCY_TARGET = 'iot-scheduler/strategy-target'
ANNOTATION_HW_REQUIRED = 'iot-scheduler/hw-required'
NODE_ANNOTATION_HW_TAGS = 'iot-scheduler/hw-tags'
ANNOTATION_ENTANGLEMENT_THRESHOLD = 'iot-scheduler/entanglement-threshold-ms'

# --- STATO CONDIVISO E THREADING ---
SHARED_OVERRIDES = {}
shared_lock = threading.Lock()
shutdown_requested = False