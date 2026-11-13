import os
import struct
import zlib


def create_diving_icon_png(filepath: str, size: int) -> None:
    """
    Genera un icono PNG válido (sin dependencias externas) con diseño
    de máscara de buceo sobre fondo océano para la PWA en Android/Desktop.
    """
    raw_rows = []
    center = size / 2.0

    for y in range(size):
        row = bytearray([0])  # Filtro PNG tipo 0 (None)
        ny = y / float(size)
        for x in range(size):
            nx = x / float(size)

            # Fondo degradado azul océano profundo
            r = int(6 + (2 - 6) * ny + 12 * (1 - nx))
            g = int(132 * (1 - 0.65 * ny))
            b = int(199 * (1 - 0.45 * ny))
            a = 255

            # Visor de máscara de buceo (rectángulo redondeado central)
            in_mask_outer = (0.16 <= nx <= 0.76) and (0.32 <= ny <= 0.64)
            in_left_lens = (0.21 <= nx <= 0.43) and (0.37 <= ny <= 0.59)
            in_right_lens = (0.49 <= nx <= 0.71) and (0.37 <= ny <= 0.59)
            in_snorkel = (0.79 <= nx <= 0.85) and (0.25 <= ny <= 0.74)

            # Círculo verde esmeralda inferior izquierdo (insignia de oferta)
            dist_badge = ((nx - 0.28) ** 2 + (ny - 0.75) ** 2) ** 0.5

            if dist_badge <= 0.12:
                r, g, b = 16, 185, 129
            elif in_left_lens or in_right_lens:
                r, g, b = 56, 189, 248
            elif in_mask_outer:
                r, g, b = 15, 23, 42
            elif in_snorkel:
                r, g, b = 245, 158, 11

            row.extend((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), a))
        raw_rows.append(bytes(row))

    raw_data = b"".join(raw_rows)

    def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat = zlib.compress(raw_data, level=9)

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + make_chunk(b"IHDR", ihdr)
        + make_chunk(b"IDAT", idat)
        + make_chunk(b"IEND", b"")
    )

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(png_bytes)


if __name__ == "__main__":
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    create_diving_icon_png(os.path.join(static_dir, "icon-192.png"), 192)
    create_diving_icon_png(os.path.join(static_dir, "icon-512.png"), 512)
    print("Iconos PWA generados correctamente en static/icon-192.png y static/icon-512.png")
