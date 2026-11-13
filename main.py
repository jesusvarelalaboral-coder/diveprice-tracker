import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl

from config import CHECK_INTERVAL_HOURS, HOST, PORT, NTFY_SERVER
from database import (
    create_item,
    delete_item,
    get_item,
    get_ntfy_topic,
    init_db,
    list_items,
    mark_item_notified,
    set_ntfy_topic,
    update_item_price,
)
from notifier import send_price_alert, send_test_notification
from scraper import scrape_price
from multisearch import search_best_prices

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("diving_tracker.main")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_candidate_static = os.path.join(BASE_DIR, "static")
STATIC_DIR = (
    _candidate_static
    if os.path.exists(os.path.join(_candidate_static, "index.html"))
    else BASE_DIR
)
scheduler = AsyncIOScheduler()
# Semáforo para no saturar la CPU/RAM si se comprueban muchos artículos a la vez
scrape_semaphore = asyncio.Semaphore(2)


class ItemCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    url: HttpUrl
    target_price: float = Field(..., gt=0)


class ConfigUpdate(BaseModel):
    ntfy_topic: str = Field(..., min_length=2, max_length=100)


async def check_single_item(item_id: int, force_notify: bool = False) -> dict:
    """Extrae el precio actual del artículo, guarda el historial y notifica si cumple objetivo."""
    item = get_item(item_id)
    if not item:
        raise ValueError(f"Artículo {item_id} no encontrado")

    async with scrape_semaphore:
        logger.info(f"Comprobando precio de [{item['id']}] {item['name']} -> {item['url']}")
        price, error = await scrape_price(item["url"])

    if price is not None:
        updated = update_item_price(item_id, price=price, status="ok", error=None)
        target = float(updated["target_price"])
        notified_event = False

        # Enviar notificación push a ntfy.sh si el precio actual baja o iguala el precio objetivo
        if price <= target:
            logger.info(
                f"¡Objetivo alcanzado para '{updated['name']}'! Actual: {price}€ <= Objetivo: {target}€"
            )
            sent = await send_price_alert(
                item_name=updated["name"],
                item_url=updated["url"],
                current_price=price,
                target_price=target,
            )
            if sent:
                mark_item_notified(item_id, price)
                updated = get_item(item_id)
                notified_event = True

        return {"item": updated, "notified": notified_event}
    else:
        updated = update_item_price(
            item_id,
            price=None,
            status="error",
            error=error or "No se pudo extraer el precio",
        )
        return {"item": updated, "notified": False}


async def scheduled_check_all_items() -> None:
    """Tarea automática ejecutada por APScheduler cada 4 horas."""
    items = list_items()
    if not items:
        logger.info("Revisión programada: no hay artículos registrados.")
        return

    logger.info(f"Iniciando revisión automática de {len(items)} artículo(s)...")
    for item in items:
        try:
            await check_single_item(item["id"])
        except Exception as exc:
            logger.error(f"Error revisando artículo {item['id']}: {exc}")
    logger.info("Revisión automática completada.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(
        scheduled_check_all_items,
        trigger=IntervalTrigger(hours=CHECK_INTERVAL_HOURS),
        id="check_all_prices_job",
        name=f"Revisar precios cada {CHECK_INTERVAL_HOURS} horas",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"APScheduler iniciado: revisión automática programada cada {CHECK_INTERVAL_HOURS} horas."
    )
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="DivePrice Tracker PWA",
    description="Rastreador de precios de tiendas de buceo online con Playwright, SQLite, APScheduler y ntfy.sh",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse(
        os.path.join(STATIC_DIR, "manifest.json"),
        media_type="application/manifest+json",
    )


@app.get("/sw.js")
async def serve_sw():
    return FileResponse(
        os.path.join(STATIC_DIR, "sw.js"),
        media_type="application/javascript",
    )


@app.get("/api/health")
async def api_health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/api/search")
async def api_search(q: str):
    clean_q = q.strip()
    if not clean_q or len(clean_q) < 2:
        raise HTTPException(status_code=400, detail="Escribe al menos 2 caracteres")
    results = await search_best_prices(clean_q)
    return {
        "query": clean_q,
        "count": len(results),
        "results": results,
    }


@app.get("/api/items")
async def api_list_items():
    job = scheduler.get_job("check_all_prices_job")
    next_run: Optional[str] = None
    if job and job.next_run_time:
        next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "items": list_items(),
        "next_scheduled_check": next_run,
        "check_interval_hours": CHECK_INTERVAL_HOURS,
    }


@app.post("/api/items")
async def api_create_item(payload: ItemCreate):
    item = create_item(
        name=payload.name,
        url=str(payload.url),
        target_price=payload.target_price,
    )
    # Comprobar inmediatamente al añadir el artículo
    result = await check_single_item(item["id"])
    return result


@app.post("/api/items/{item_id}/check")
async def api_check_item(item_id: int):
    item = get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    result = await check_single_item(item_id)
    return result


@app.post("/api/check-all")
async def api_check_all():
    items = list_items()
    results = []
    for item in items:
        res = await check_single_item(item["id"])
        results.append(res)
    return {"checked": len(results), "results": results}


@app.delete("/api/items/{item_id}")
async def api_delete_item(item_id: int):
    deleted = delete_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    return {"deleted": True, "id": item_id}


@app.get("/api/config")
async def api_get_config():
    job = scheduler.get_job("check_all_prices_job")
    next_run = (
        job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
        if job and job.next_run_time
        else None
    )
    return {
        "ntfy_topic": get_ntfy_topic(),
        "ntfy_server": NTFY_SERVER,
        "check_interval_hours": CHECK_INTERVAL_HOURS,
        "next_scheduled_check": next_run,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/api/config")
async def api_update_config(payload: ConfigUpdate):
    topic = set_ntfy_topic(payload.ntfy_topic)
    return {"ntfy_topic": topic, "ntfy_server": NTFY_SERVER}


@app.post("/api/config/test-notification")
async def api_test_notification():
    ok = await send_test_notification()
    if not ok:
        raise HTTPException(
            status_code=502,
            detail="No se pudo enviar la notificación a ntfy.sh. Comprueba tu conexión o el nombre del tema.",
        )
    return {"ok": True, "topic": get_ntfy_topic()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
