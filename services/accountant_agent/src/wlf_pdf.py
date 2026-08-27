"""Replace only the issuer header of an original Wave PDF for WLF invoices."""
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.pdfgen import canvas


def brand_wlf_wave_pdf(wave_pdf: bytes, logo_path: str) -> bytes:
    """Preserve Wave's invoice layout and replace only its first-page header."""
    source = PdfReader(BytesIO(wave_pdf))
    first = source.pages[0]
    width, height = float(first.mediabox.width), float(first.mediabox.height)
    overlay = BytesIO()
    c = canvas.Canvas(overlay, pagesize=(width, height))
    header_bottom = height - 190
    c.setFillColor(colors.white)
    c.rect(0, header_bottom, width, height-header_bottom, fill=1, stroke=0)
    c.drawImage(logo_path, 28, height-105, width=190, height=55,
                preserveAspectRatio=True, anchor="w", mask="auto")
    right = width-28
    c.setFillColor(colors.black); c.setFont("Helvetica", 28)
    c.drawRightString(right, height-48, "INVOICE")
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(right, height-82, "World Lawyers Forum")
    c.setFont("Helvetica", 8.2)
    c.drawRightString(right, height-96, "Managed by International Intellectual Property Law Association, Inc. (IIPLA)")
    c.drawRightString(right, height-112, "589 S 22nd St, San Jose, California 95116, USA")
    c.drawRightString(right, height-128, "Phone: +1 888 355 0013")
    c.drawRightString(right, height-144, "Email: mail@worldlawyersforum.org")
    c.drawRightString(right, height-160, "Website: worldlawyersforum.org")
    c.setStrokeColor(colors.HexColor("#d9dde1")); c.setLineWidth(.7)
    c.line(0, header_bottom, width, header_bottom); c.save(); overlay.seek(0)
    first.merge_page(PdfReader(overlay).pages[0], over=True)
    writer=PdfWriter()
    for page in source.pages: writer.add_page(page)
    result=BytesIO(); writer.write(result); return result.getvalue()
