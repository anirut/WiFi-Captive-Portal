"""PDF + QR voucher generation using reportlab and qrcode."""
import io
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors


def _make_qr_image(data: str) -> Image:
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=3 * cm, height=3 * cm)


def generate_voucher_pdf(
    vouchers: list[dict],
    qr_mode: str = "code",
    portal_url: str = "http://portal.local",
) -> bytes:
    """
    vouchers: list of {code, type, duration_minutes, data_limit_mb}
    qr_mode: "code" (QR encodes code string) | "url" (QR encodes portal URL with code)
    Returns: PDF bytes
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1 * cm, rightMargin=1 * cm,
                            topMargin=1 * cm, bottomMargin=1 * cm)
    styles = getSampleStyleSheet()
    elements = []

    for v in vouchers:
        code = v["code"]
        vtype = v.get("type", "time")
        limit = v.get("duration_minutes") if vtype == "time" else v.get("data_limit_mb")
        unit = "min" if vtype == "time" else "MB"
        qr_data = f"{portal_url}/?code={code}" if qr_mode == "url" else code
        qr_img = _make_qr_image(qr_data)

        data = [
            [qr_img, Paragraph(f"<b>WiFi Voucher</b><br/>Code: <b>{code}</b><br/>"
                               f"Type: {vtype} | Limit: {limit} {unit}", styles["Normal"])],
        ]
        table = Table(data, colWidths=[4 * cm, 14 * cm])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5 * cm))

    doc.build(elements)
    return buf.getvalue()
