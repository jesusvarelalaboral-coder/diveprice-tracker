import asyncio
import logging
import re
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright

from scraper import parse_price_string

logger = logging.getLogger("diving_tracker.multisearch")


def _calculate_relevance(title: str, query: str) -> int:
    """Calcula una puntuación de coincidencia de palabras entre el título y la búsqueda."""
    title_lower = title.lower()
    tokens = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 1]
    if not tokens:
        return 1
    score = 0
    for tok in tokens:
        if tok in title_lower:
            score += 2
            # Bonus si es palabra exacta
            if re.search(r"\b" + re.escape(tok) + r"\b", title_lower):
                score += 3
    return score


def _search_casco_antiguo(browser, query: str) -> List[Dict[str, Any]]:
    """Busca productos en Casco Antiguo."""
    results = []
    try:
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-ES",
        )
        page = context.new_page()
        encoded = quote_plus(query)
        url = f"https://www.cascoantiguo.com/es/busqueda?s={encoded}"
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2500)

        raw_items = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('.product-miniature, .js-product-miniature')).map(el => {
                const link = el.querySelector('h2 a, h3 a, .product-title a, a');
                const priceEl = el.querySelector('.price, .current-price, [itemprop="price"]');
                const img = el.querySelector('img');
                const title = (link ? link.innerText.trim() : '') || (img ? img.alt : '');
                return {
                    title: title,
                    price: priceEl ? priceEl.innerText.trim() : '',
                    url: link ? link.href : '',
                    image: img ? (img.getAttribute('src') || img.getAttribute('data-src') || '') : ''
                };
            }).filter(x => x.title && x.price);
        }""")
        context.close()

        for item in raw_items:
            price_val = parse_price_string(item["price"])
            if price_val:
                rel = _calculate_relevance(item["title"], query)
                results.append({
                    "store": "Casco Antiguo",
                    "store_id": "cascoantiguo",
                    "title": item["title"],
                    "price": price_val,
                    "url": item["url"],
                    "image": item.get("image", ""),
                    "relevance": rel,
                })
    except Exception as exc:
        logger.warning(f"Error buscando en Casco Antiguo: {exc}")
    return results


def _search_diveinn(browser, query: str) -> List[Dict[str, Any]]:
    """Busca productos en Diveinn / Scubastore (Tradeinn)."""
    results = []
    try:
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-ES",
        )
        page = context.new_page()
        encoded = quote_plus(query)
        url = f"https://www.tradeinn.com/diveinn/es/buscar?q={encoded}"
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2500)

        raw_items = page.evaluate("""() => {
            const list = [];
            document.querySelectorAll('a[href*="/diveinn/es/"]').forEach(a => {
                const text = a.innerText || '';
                const href = a.href;
                if (href.endsWith('/p') && text.includes('€')) {
                    const parts = text.split('\\n').map(s => s.trim()).filter(Boolean);
                    const pricePart = parts.find(p => p.includes('€'));
                    const titlePart = parts.find(p => !p.includes('€') && p.length > 5);
                    const img = a.querySelector('img') || a.parentElement.querySelector('img');
                    if (pricePart && titlePart) {
                        list.push({
                            title: titlePart,
                            price: pricePart,
                            url: href,
                            image: img ? (img.src || img.getAttribute('data-src') || '') : ''
                        });
                    }
                }
            });
            const seen = new Set();
            return list.filter(r => {
                if (seen.has(r.url)) return false;
                seen.add(r.url);
                return true;
            });
        }""")
        context.close()

        for item in raw_items:
            price_val = parse_price_string(item["price"])
            if price_val:
                rel = _calculate_relevance(item["title"], query)
                results.append({
                    "store": "Diveinn / Scubastore",
                    "store_id": "diveinn",
                    "title": item["title"],
                    "price": price_val,
                    "url": item["url"],
                    "image": item.get("image", ""),
                    "relevance": rel,
                })
    except Exception as exc:
        logger.warning(f"Error buscando en Diveinn: {exc}")
    return results


def _search_gidive(browser, query: str) -> List[Dict[str, Any]]:
    """Busca productos en Gidive Store."""
    results = []
    try:
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-ES",
        )
        page = context.new_page()
        encoded = quote_plus(query)
        url = f"https://www.gidivestore.com/eu/es/buscar?controller=search&s={encoded}"
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2500)

        raw_items = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('.product-miniature, article.product-miniature')).map(el => {
                const link = el.querySelector('a.thumbnail') || el.querySelector('a');
                const priceEl = el.querySelector('.price, .current-price, [itemprop="price"]');
                const img = el.querySelector('img');
                const title = (img ? img.alt : '') || (el.querySelector('.product-title') ? el.querySelector('.product-title').innerText.trim() : '');
                return {
                    title: title,
                    price: priceEl ? priceEl.innerText.trim() : '',
                    url: link ? link.href : '',
                    image: img ? (img.getAttribute('src') || img.getAttribute('data-src') || '') : ''
                };
            }).filter(x => x.title && x.price);
        }""")
        context.close()

        for item in raw_items:
            price_val = parse_price_string(item["price"])
            if price_val:
                rel = _calculate_relevance(item["title"], query)
                results.append({
                    "store": "Gidive Store",
                    "store_id": "gidive",
                    "title": item["title"],
                    "price": price_val,
                    "url": item["url"],
                    "image": item.get("image", ""),
                    "relevance": rel,
                })
    except Exception as exc:
        logger.warning(f"Error buscando en Gidive: {exc}")
    return results


def _search_all_stores_sync(query: str) -> List[Dict[str, Any]]:
    """Ejecuta la búsqueda multitienda en Playwright de forma síncrona."""
    clean_query = query.strip()
    if not clean_query:
        return []

    combined_results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-zygote",
            ],
        )

        # Ejecutamos las búsquedas secuenciales o en pestañas separadas
        diveinn_items = _search_diveinn(browser, clean_query)
        casco_items = _search_casco_antiguo(browser, clean_query)
        gidive_items = _search_gidive(browser, clean_query)

        browser.close()

        combined_results.extend(diveinn_items)
        combined_results.extend(casco_items)
        combined_results.extend(gidive_items)

    # Filtrar resultados con coincidencia relevante con el producto buscado
    # Si hay resultados con relevancia > 0, descartamos los de 0 para no mostrar ruido
    has_matches = any(r["relevance"] > 0 for r in combined_results)
    if has_matches:
        filtered = [r for r in combined_results if r["relevance"] > 0]
    else:
        filtered = combined_results

    # Ordenar por precio ascendente (el más barato primero)
    filtered.sort(key=lambda x: (x["price"], -x["relevance"]))
    return filtered


async def search_best_prices(query: str) -> List[Dict[str, Any]]:
    """Buscador asíncrono para ejecutar en un hilo sin bloquear FastAPI."""
    return await asyncio.to_thread(_search_all_stores_sync, query)
