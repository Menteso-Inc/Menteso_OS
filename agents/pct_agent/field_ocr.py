"""Whole labelled-field OCR agreement, with bounded fallback to vision.

This path is opt-in. Email always needs the original independent vision check.
The two engines must read the entire bounded value area, not an OCR text line.
"""
from __future__ import annotations

import re
import threading
import time

_ENGINE = None
_LOCK = threading.Lock()


def bounds_for(scan, block, kind):
    from . import local_evidence as local
    if kind not in {'name', 'phone'} or not block.get(kind):
        return None
    lookup = {l['id']: l for l in scan['lines']}
    heading = lookup[block['section']]
    page = next(p for p in scan['pages'] if p['page'] == heading['page'])
    lines = [l for l in scan['lines'] if l['page'] == heading['page']]
    stops = [l['rect'][1] for l in lines if l['rect'][1] > heading['rect'][1] + 8
             and abs(l['rect'][0] - heading['rect'][0]) < 15
             and len(l['text']) < 100 and local.SECTION_STOP.search(l['text'])
             and not local.qualified_role(l['text'])]
    section_end = min(stops) if stops else page['height']
    labels = [l for l in lines if heading['rect'][1] + 4 < l['rect'][1] < section_end - 2
              and abs(l['rect'][0] - heading['rect'][0]) < 15
              and len(l['text']) < 100 and local.FIELD_STOP.search(l['text'])]
    matches = [l for l in labels if local.FIELD_LABELS[kind].search(l['text'])]
    if len(matches) != 1:
        return None
    label = matches[0]
    following = [l['rect'][1] for l in labels if l['rect'][1] > label['rect'][1] + 4]
    if not following:
        return None  # An unbounded field must use the existing verifier.
    end = min(following)
    values = [lookup[i] for i in block[kind]]
    if any(l['page'] != heading['page'] or l['rect'][0] <= label['rect'][2] + 8
           or l['rect'][1] < label['rect'][1] - 3 or l['rect'][3] >= end - 1 for l in values):
        return None
    left = min(l['rect'][0] for l in values) - 3
    rect = [left, min(label['rect'][1], min(l['rect'][1] for l in values)) - 2, page['width'] - 1, end - 1]
    if not 9 <= rect[3] - rect[1] <= 100 or rect[2] - left < 25:
        return None
    # The ePCT layout has one value column. A label in the proposed value band
    # indicates a side-by-side form and is not safe for this shortcut.
    if any(l['id'] not in block[kind] and l['rect'][0] >= left
           and rect[1] <= l['rect'][1] < rect[3]
           and local.FIELD_STOP.search(l['text']) for l in lines):
        return None
    return {'page': page['page'], 'rect': rect, 'label_id': label['id'],
            'next_label_y': end, 'method': 'complete_labelled_value_band'}


def line_regions(image):
    """Account for every ink band in a known field, without a neural detector."""
    import numpy as np
    ink=np.asarray(image.convert('L'))<220
    if ink.size==0:return []
    # Ignore full-height/width form rules only when locating text. Recognition
    # still uses original pixels. Text strokes do not span the complete field.
    ink[:,ink.mean(axis=0)>.9]=False
    ink[ink.mean(axis=1)>.9,:]=False
    rows=np.flatnonzero(ink.sum(axis=1)>=2)
    if not len(rows):return []
    bands=[];start=previous=int(rows[0])
    for y in map(int,rows[1:]):
        if y-previous>4:bands.append((start,previous+1));start=y
        previous=y
    bands.append((start,previous+1))
    regions=[]
    for y0,y1 in bands:
        columns=np.flatnonzero(ink[y0:y1].any(axis=0))
        x0,x1=int(columns[0]),int(columns[-1])+1
        # Noise, clipping or an almost empty value area goes to vision.
        if y1-y0<5 or x1-x0<3 or min(x0,y0)<=2 or x1>=image.width-2 or y1>=image.height-2:
            return []
        regions.append([x0,y0,x1,y1])
    return regions


def remove_table_rules(image):
    """Remove only complete thin form rules; retain the original evidence crop."""
    import numpy as np
    pixels=np.array(image.convert('RGB'))
    ink=np.asarray(image.convert('L'))<180
    # Text has whitespace above/below it in a complete field. Only uninterrupted
    # rules spanning the entire crop qualify; groups wider than 3 px are kept.
    for axis in (0, 1):
        positions=np.flatnonzero(ink.mean(axis=axis)>.98)
        groups=[]
        for pos in positions:
            if not groups or pos>groups[-1][-1]+1:groups.append([])
            groups[-1].append(int(pos))
        for group in groups:
            if len(group)<=3:
                if axis==0:pixels[:,group,:]=255
                else:pixels[group,:,:]=255
    from PIL import Image
    return Image.fromarray(pixels)


def recognize(image, remove_rules=False):
    global _ENGINE
    import winocr
    from rapidocr import RapidOCR
    started = time.monotonic()
    if remove_rules:
        image=remove_table_rules(image)
    windows = winocr.recognize_pil_sync(image, 'en')
    regions=line_regions(image)
    if not regions:
        return {'windows':[],'rapidocr':[],'width':image.width,'height':image.height,
                'seconds':round(time.monotonic()-started,4),'coverage':'unconfirmed'}
    rapid=[]
    with _LOCK:
        if _ENGINE is None:
            _ENGINE = RapidOCR(params={'Global.log_level': 'error',
                'EngineConfig.onnxruntime.intra_op_num_threads': 2,
                'EngineConfig.onnxruntime.inter_op_num_threads': 1})
        for x0,y0,x1,y1 in regions:
            result=_ENGINE(image.crop((x0-2,y0-2,x1+2,y1+2)),use_det=False,use_cls=False,use_rec=True)
            texts=list(result.txts or [])
            scores=list(result.scores) if result.scores is not None else []
            rapid.append({'text':texts[0] if len(texts)==1 else '',
                          'score':float(scores[0]) if len(scores)==1 else 0,
                          'rect':[x0,y0,x1,y1]})
    rapid.sort(key=lambda l: (round(l['rect'][1] / 5), l['rect'][0]))
    win_lines = []
    for line in windows.get('lines', []):
        boxes = [w['bounding_rect'] for w in line.get('words', [])]
        if not boxes or not line.get('text', '').strip():
            continue
        win_lines.append({'text': line['text'], 'rect': [min(b['x'] for b in boxes),
            min(b['y'] for b in boxes), max(b['x'] + b['width'] for b in boxes),
            max(b['y'] + b['height'] for b in boxes)]})
    win_lines.sort(key=lambda l: (round(l['rect'][1] / 5), l['rect'][0]))
    return {'windows': win_lines, 'rapidocr': rapid, 'width': image.width, 'height': image.height,
            'seconds': round(time.monotonic() - started, 4),
            'coverage':'every_nonborder_ink_band','ink_regions':regions}


def agrees_with_source(source, reading):
    """Windows whole-page OCR can corroborate a complete RapidOCR cell reading."""
    rapid=reading.get('rapidocr', [])
    if reading.get('coverage')!='every_nonborder_ink_band' or not rapid:
        return None
    if any(not .995<=line.get('score',0)<=1 for line in rapid):
        return None
    for line in rapid:
        x0,y0,x1,y1=line['rect']
        if min(x0,y0)<=2 or x1>=reading['width']-2 or y1>=reading['height']-2:
            return None
    text=' '.join(line['text'] for line in rapid).strip()
    norm=lambda value:' '.join(value.split()).casefold()
    return text if text and norm(text)==norm(source) else None


def accepted_value(kind, reading):
    if kind not in {'name', 'phone'}:
        return None
    windows = reading.get('windows', []); rapid = reading.get('rapidocr', [])
    if not windows or not rapid or any(not .995 <= l['score'] <= 1 for l in rapid):
        return None
    width, height = reading['width'], reading['height']
    for line in windows + rapid:
        x0, y0, x1, y1 = line['rect']
        if min(x0, y0) <= 2 or x1 >= width - 2 or y1 >= height - 2:
            return None  # Possible clipped characters cannot be accepted.
    # Do not discard punctuation/accents or guess similar characters.
    norm = lambda s: ' '.join(s.split()).casefold()
    first = ' '.join(l['text'] for l in windows).strip()
    second = ' '.join(l['text'] for l in rapid).strip()
    if not first or norm(first) != norm(second):
        return None
    if kind == 'phone' and (not re.fullmatch(r'[+()\d\s./-]+', first)
                            or not 7 <= len(re.sub(r'\D', '', first)) <= 20):
        return None
    if kind == 'name' and (not any(c.isalpha() for c in first)
                           or len(first) > 300 or '@' in first):
        return None
    return first
