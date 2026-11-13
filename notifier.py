import logging
import httpx
from config import NTFY_SERVER
from database import get_ntfy_topic

logger = logging.getLogger("diving_tracker.notifier")


async def send_price_alert(
    item_name: str,
    item_url: str,
    current_price: float,
    target_price: float,
) -> bool:
    """
    Envía una notificación push mediante HTTP POST a https://ntfy.sh/{topic}
    cuando el precio actual iguala o baja del precio objetivo.
    """
    topic = get_ntfy_topic()
    if not topic:
        logger.warning("No hay tema ntfy configurado. Omitiendo notificación.")
        return False

    endpoint = f"{NTFY_SERVER.rstrip('/')}/{topic}"
    diff = round(target_price - current_price, 2)
    ahorro_txt = f" (¡{diff:.2f} € por debajo de tu objetivo!)" if diff > 0 else " (¡Ha alcanzado tu objetivo!)"

    message = (
        f"🤿 ¡Oferta de buceo detectada!\n"
        f"Artículo: {item_name}\n"
        f"💰 Precio actual: {current_price:.2f} €\n"
        f"🎯 Tu objetivo: {target_price:.2f} €{ahorro_txt}\n"
        f"🔗 {item_url}"
    )

    headers = {
        "Title": f"Bajada de precio: {item_name[:50]} ({current_price:.2f} EUR)",
        "Priority": "high",
        "Tags": "diving_mask,money_with_wings,tada",
        "Click": item_url,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                endpoint,
                content=message.encode("utf-8"),
                headers=headers,
            )
            response.raise_for_status()
            logger.info(f"Notificación enviada a {endpoint} para '{item_name}'")
            return True
    except Exception as exc:
        logger.error(f"Error enviando notificación a ntfy.sh ({endpoint}): {exc}")
        return False


async def send_test_notification() -> bool:
    """Envía una notificación de prueba al tema configurado en ntfy.sh."""
    topic = get_ntfy_topic()
    endpoint = f"{NTFY_SERVER.rstrip('/')}/{topic}"
    message = (
        "🤿 ¡Conexión correcta con DivePrice Tracker!\n"
        f"Recibirás alertas en el canal '{topic}' cada vez que un equipo de buceo baje de tu precio objetivo."
    )
    headers = {
        "Title": "Prueba de DivePrice Tracker",
        "Priority": "default",
        "Tags": "diving_mask,white_check_mark",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                endpoint,
                content=message.encode("utf-8"),
                headers=headers,
            )
            response.raise_for_status()
            return True
    except Exception as exc:
        logger.error(f"Error en notificación de prueba a ntfy.sh: {exc}")
        return False
