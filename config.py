import os

# ==============================================================================
# CONFIGURACIÓN PRINCIPAL DE LA APLICACIÓN
# ==============================================================================

# Tema de ntfy.sh donde se enviarán las alertas de bajada de precio.
# Puedes suscribirte en la app móvil de ntfy o en https://ntfy.sh/<NTFY_TOPIC>
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "buceo-ofertas-alertas")

# Servidor ntfy (por defecto el servidor público oficial)
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")

# Intervalo de revisión automática en segundo plano (en horas)
CHECK_INTERVAL_HOURS = int(os.getenv("CHECK_INTERVAL_HOURS", "4"))

# Ruta de la base de datos SQLite
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diving_tracker.db")

# Escuchar en 0.0.0.0 permite abrir la app tanto en el PC (127.0.0.1) como desde el móvil por Wi-Fi
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
