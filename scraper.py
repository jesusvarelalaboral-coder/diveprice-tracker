import asyncio
import json
import re
import logging
from typing import Optional, Tuple
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger("diving_tracker.scraper")


def parse_price_string(raw: str) -> Optional[float]:
    """
    Convierte un texto de precio (ej. '1.249,95 €', '249.99', 'EUR 89,50')
    en un float válido en euros.
    """
    if not raw:
        return None
    text = str(raw).strip()
    # Ignorar textos que claramente son cuotas o meses (ej. "12 cuotas de 15€")
    lower = text.lower()
    if any(k in lower for k in ["cuota", "/mes", "mensual", "financi", "ahorra", "descuento"]):
        return None

    # Buscar patrones numéricos con separadores de miles/decimales
    matches = re.findall(r"(?<!\d)(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})|\d+)(?!\d)", text)
    if not matches:
        return None

    candidate = matches[0]
    # Determinar separador decimal vs separador de miles
    if "," in candidate and "." in candidate:
        if candidate.rfind(",") > candidate.rfind("."):
            # Formato europeo: 1.234,56
            candidate = candidate.replace(".", "").replace(",", ".")
        else:
            # Formato anglosajón: 1,234.56
            candidate = candidate.replace(",", "")
    elif "," in candidate:
        parts = candidate.split(",")
        if len(parts[-1]) in (1, 2):
            candidate = candidate.replace(",", ".")
        else:
            candidate = candidate.replace(",", "")
    elif "." in candidate:
        parts = candidate.split(".")
        if len(parts[-1]) == 3 and len(parts[0]) <= 3:
            # Posible separador de miles sin decimales: 1.250
            candidate = candidate.replace(".", "")

    try:
        val = float(candidate)
        if 0.5 <= val <= 25000:
            return round(val, 2)
    except ValueError:
        return None
    return None


def _extract_from_jsonld(data: object) -> Optional[float]:
    """Busca recursivamente objetos Product / Offer en estructuras JSON-LD."""
    if isinstance(data, list):
        for elem in data:
            res = _extract_from_jsonld(elem)
            if res is not None:
                return res
    elif isinstance(data, dict):
        # Si tiene @graph, explorar
        if "@graph" in data:
            res = _extract_from_jsonld(data["@graph"])
            if res is not None:
                return res

        obj_type = str(data.get("@type", "")).lower()
        if "product" in obj_type or "offer" in obj_type or "offers" in data:
            offers = data.get("offers")
            if offers:
                res = _extract_from_jsonld(offers)
                if res is not None:
                    return res

            for key in ("price", "lowPrice", "highPrice"):
                if key in data and data[key] is not None:
                    parsed = parse_price_string(str(data[key]))
                    if parsed is not None:
                        return parsed

            # Algunos sitios guardan el precio dentro de priceSpecification
            if "priceSpecification" in data:
                res = _extract_from_jsonld(data["priceSpecification"])
                if res is not None:
                    return res
    return None


# Selectores específicos y generales de tiendas de buceo y e-commerce (PrestaShop, WooCommerce, Shopify, Tradeinn/Scubastore, Casco Antiguo, Decathlon, etc.)
PRICE_SELECTORS = [
    # Scubastore / Tradeinn
    "#js-precio",
    ".precio_actual",
    ".ficha_precio_actual",
    "[data-ta='product-price']",
    # PrestaShop (Casco Antiguo, Gidive, etc.)
    ".current-price-value",
    ".current-price span[itemprop='price']",
    ".current-price .price",
    "#our_price_display",
    ".product-prices .price",
    # WooCommerce
    "p.price ins .woocommerce-Price-amount",
    "p.price .woocommerce-Price-amount",
    ".summary .price ins .amount",
    ".summary .price .amount",
    # Magento / Adobe Commerce
    "[data-price-type='finalPrice'] .price",
    ".special-price .price",
    ".price-box .price",
    # Shopify
    ".price__sale .price-item--sale",
    ".price__regular .price-item--regular",
    ".product__price",
    ".product-single__price",
    # Decathlon / Grandes tiendas
    ".prc__active-price",
    "[data-testid='product-price']",
    # Genéricos con microdatos o atributos
    "[itemprop='price']",
    "[data-price-amount]",
    "[data-product-price]",
    ".product-price-current",
    ".product-price",
    ".sale-price",
    ".final-price",
    ".price-current",
    ".price",
]


def _scrape_price_sync(url: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Ejecuta Playwright en modo headless para extraer el precio de la URL.
    Retorna (precio, mensaje_error).
    """
    try:
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
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="es-ES",
                viewport={"width": 1366, "height": 900},
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Esperar brevemente a que hidraten precios dinámicos por JS
                page.wait_for_timeout(2000)
            except PlaywrightTimeoutError:
                logger.warning(f"Timeout parcial cargando {url}, intentando extraer del DOM actual...")

            # 1) Estrategia Schema.org JSON-LD (<script type="application/ld+json">)
            scripts = page.locator("script[type='application/ld+json']").all_inner_texts()
            for raw_json in scripts:
                try:
                    cleaned = raw_json.strip()
                    if not cleaned:
                        continue
                    data = json.loads(cleaned)
                    price = _extract_from_jsonld(data)
                    if price is not None:
                        browser.close()
                        return price, None
                except Exception:
                    continue

            # 2) Estrategia Meta Tags & Microdata (OpenGraph, Schema itemprop="price" content="...")
            meta_selectors = [
                "meta[property='product:price:amount']",
                "meta[property='og:price:amount']",
                "meta[name='twitter:data1']",
                "[itemprop='price'][content]",
                "[data-price-amount]",
            ]
            for sel in meta_selectors:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    val = (
                        loc.get_attribute("content")
                        or loc.get_attribute("data-price-amount")
                        or ""
                    )
                    price = parse_price_string(val)
                    if price is not None:
                        browser.close()
                        return price, None

            # 3) Estrategia Selectores habituales de tiendas de buceo y e-commerce
            for sel in PRICE_SELECTORS:
                try:
                    elements = page.locator(sel).all()
                    for el in elements[:5]:
                        if not el.is_visible():
                            continue
                        # Revisar atributos directos primero
                        for attr in ("content", "data-price-amount", "data-price"):
                            attr_val = el.get_attribute(attr)
                            if attr_val:
                                p_val = parse_price_string(attr_val)
                                if p_val is not None:
                                    browser.close()
                                    return p_val, None
                        # Revisar texto visible
                        txt = el.inner_text()
                        p_val = parse_price_string(txt)
                        if p_val is not None:
                            browser.close()
                            return p_val, None
                except Exception:
                    continue

            # 4) Estrategia Heurística en el DOM: buscar elementos visibles con símbolo €
            js_candidates = page.evaluate(
                """() => {
                    const results = [];
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                    let node;
                    while ((node = walker.nextNode())) {
                        const tag = node.tagName.toLowerCase();
                        if (['script', 'style', 'noscript', 'del', 's', 'strike'].includes(tag)) continue;
                        if (node.children.length > 2) continue;
                        const text = (node.innerText || '').trim();
                        if (!text || text.length > 35) continue;
                        if (text.includes('€') || text.includes('EUR')) {
                            const style = window.getComputedStyle(node);
                            if (style.display === 'none' || style.visibility === 'hidden' || style.textDecorationLine.includes('line-through')) {
                                continue;
                            }
                            const fontSize = parseFloat(style.fontSize) || 14;
                            results.push({ text, fontSize });
                        }
                    }
                    // Ordenar priorizando el texto con mayor tamaño de fuente (suele ser el precio principal del producto)
                    results.sort((a, b) => b.fontSize - a.fontSize);
                    return results.slice(0, 15).map(r => r.text);
                }"""
            )
            for candidate_text in js_candidates:
                p_val = parse_price_string(candidate_text)
                if p_val is not None:
                    browser.close()
                    return p_val, None

            browser.close()
            return None, "No se pudo detectar ningún precio en la página."

    except Exception as exc:
        logger.exception(f"Error haciendo scraping de {url}")
        return None, f"Error de navegador: {str(exc)[:180]}"


async def scrape_price(url: str) -> Tuple[Optional[float], Optional[str]]:
    """Envoltorio asíncrono seguro para ejecutar Playwright en un hilo."""
    return await asyncio.to_thread(_scrape_price_sync, url)
