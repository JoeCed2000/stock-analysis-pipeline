from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import fitz


OUT = "reports/generated/emoji_test.pdf"
FONT = "/mnt/c/Windows/Fonts/seguiemj.ttf"

pdfmetrics.registerFont(TTFont("SegoeUIEmoji", FONT))
c = canvas.Canvas(OUT)
c.setFont("SegoeUIEmoji", 20)
s = "\U0001F31F \u26A0\uFE0F \U0001F9E0 \U0001F3AF \U0001F4CA \U0001F4B0 \U0001F4C8 \U0001F4E6 \U0001F52E \U0001F3C6 \U0001F449 \u25CF \u2460\u2461\u2462"
c.drawString(72, 750, s)
c.save()

d = fitz.open(OUT)
print(d[0].get_text())
