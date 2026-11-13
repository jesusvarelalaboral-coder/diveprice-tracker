# Imagen oficial de Python ligera
FROM python:3.12-slim

# Evitar archivos .pyc y habilitar logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

WORKDIR /app

# Instalar dependencias del sistema necesarias para Chromium (Playwright)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium

# Copiar el código de la aplicación
COPY . .

# Si los archivos estáticos se subieron en la raíz sin carpeta static/, organizarlos automáticamente
RUN mkdir -p static && \
    for f in index.html manifest.json sw.js icon.svg icon-192.png icon-512.png; do \
        if [ -f "$f" ] && [ ! -f "static/$f" ]; then cp "$f" "static/$f"; fi; \
    done

# Generar los iconos PWA por seguridad si no existen
RUN python generate_icons.py

EXPOSE 8000

# Arrancar FastAPI con Uvicorn usando la variable PORT que asigne la nube (por defecto 8000)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
