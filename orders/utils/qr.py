# orders/utils/qr.py
import qrcode
from io import BytesIO
import base64

def generate_qr_base64(data: str) -> str:
    """Generate a QR code and return it as a base64-encoded PNG string."""
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
