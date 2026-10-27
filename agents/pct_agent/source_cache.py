"""Reuse immutable source PDFs only after matching the filing's application ID."""
import hashlib
import io
import re
from pathlib import Path

import fitz
from PIL import Image


def application_key(value):
    value=re.sub('[^A-Z0-9]','',str(value).upper())
    return value.removeprefix('PCT')


def validated_source(path, application, vision_reader=None):
    """The PDF's own first page, not its filename/old result, proves identity."""
    import winocr
    expected=application_key(application)
    if not re.fullmatch(r'[A-Z]{2}\d{10}',expected):
        raise ValueError('Unsupported application identity')
    path=Path(path)
    visual_evidence=None
    with fitz.open(path) as doc:
        if not len(doc):raise ValueError('Empty source PDF')
        page_count=len(doc)
        text=doc[0].get_text()
        if expected not in application_key(text):
            pix=doc[0].get_pixmap(matrix=fitz.Matrix(3,3),alpha=False)
            ocr=winocr.recognize_pil_sync(Image.open(io.BytesIO(pix.tobytes('png'))),'en')
            text=ocr.get('text','')
            if expected not in application_key(text) and vision_reader:
                for line in ocr.get('lines',[]):
                    boxes=[w['bounding_rect'] for w in line.get('words',[])]
                    if not boxes or min(b['y'] for b in boxes)>pix.height*.5:continue
                    if not re.search(r'PCT\s*/\s*[A-Zl1]{2}\s*2|[A-Zl1]{2}\s*20\d{2}[/ ]',line['text']):continue
                    rect=fitz.Rect(min(b['x'] for b in boxes)/3-5,min(b['y'] for b in boxes)/3-5,
                        max(b['x']+b['width'] for b in boxes)/3+5,max(b['y']+b['height'] for b in boxes)/3+5)
                    data=doc[0].get_pixmap(matrix=fitz.Matrix(4,4),clip=rect,alpha=False).tobytes('png')
                    reading,meta=vision_reader(data,'application number')
                    if reading.get('legible') is True and application_key(reading.get('text',''))==expected:
                        text=reading['text'];visual_evidence={'reading':reading,'timing':meta};break
        if expected not in application_key(text):
            raise ValueError('Source PDF application does not match input')
    return {'application':expected,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'pages':page_count,'identity_visual_check':visual_evidence}
