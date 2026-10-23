"""Optional, pinned Cyrillic OCR for documents with unreadable role headings.

The recognizer is installed separately; no model is downloaded at run time.
OCR supplies source lines only. Existing original-image contact verification
and ownership checks still decide whether any value can be exported.
"""
import hashlib
import os
import re
import threading
from pathlib import Path

MODEL_SHA256 = '90f761b4bfcce0c8c561c0cb5c887b0971d3ec01c32164bdf7374a35b0982711'
_ENGINE = None
_ENGINE_PATH = None
_LOCK = threading.Lock()


def model_path():
    value = os.getenv('PCT_OLLAMA_CYRILLIC_OCR_MODEL', '').strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
        raise RuntimeError('ollama_cyrillic_ocr_model_unverified')
    return path


def cache_material():
    return {'enabled': bool(model_path()), 'sha256': MODEL_SHA256 if os.getenv('PCT_OLLAMA_CYRILLIC_OCR_MODEL', '').strip() else None}


def recognize(image):
    global _ENGINE, _ENGINE_PATH
    import rapidocr
    from rapidocr import RapidOCR, OCRVersion, ModelType, LangRec
    path = model_path()
    if path is None:
        raise RuntimeError('ollama_cyrillic_ocr_not_configured')
    defaults = Path(rapidocr.__file__).parent / 'models'
    detector = defaults / 'PP-OCRv6_det_small.onnx'
    classifier = defaults / 'ch_ppocr_mobile_v2.0_cls_mobile.onnx'
    if not detector.is_file() or not classifier.is_file():
        raise RuntimeError('ollama_cyrillic_ocr_dependencies_missing')
    with _LOCK:
        if _ENGINE is None or _ENGINE_PATH != path:
            _ENGINE = RapidOCR(params={
                'Global.log_level': 'error', 'Global.model_root_dir': str(path.parent),
                'Det.model_path': str(detector), 'Cls.model_path': str(classifier),
                'Rec.ocr_version': OCRVersion.PPOCRV5, 'Rec.model_type': ModelType.MOBILE,
                'Rec.lang_type': LangRec.CYRILLIC, 'Rec.model_path': str(path),
                'EngineConfig.onnxruntime.intra_op_num_threads': 1,
                'EngineConfig.onnxruntime.inter_op_num_threads': 1})
            _ENGINE_PATH = path
        result = _ENGINE(image)
    lines = []
    if result.txts is None:
        return {'text': '', 'lines': []}
    for box, text, confidence in zip(result.boxes, result.txts, result.scores):
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        lines.append({'text': text, 'confidence': float(confidence), 'words': [
            {'text': text, 'bounding_rect': {'x': min(xs), 'y': min(ys),
                'width': max(xs) - min(xs), 'height': max(ys) - min(ys)}}]})
    return {'text': '\n'.join(line['text'] for line in lines), 'lines': lines}


def choose_scan(pdf_path, original, step):
    from . import local_evidence as local
    if not os.getenv('PCT_OLLAMA_CYRILLIC_OCR_MODEL', '').strip():
        return original, None
    if any(local.role_headings([line for line in original['lines'] if line['page'] == page['page']],
                               page['width']) for page in original['pages']):
        return original, None
    material = cache_material()
    step('[AI Verification] No confirmed role headings; checking original pages with Cyrillic OCR')
    candidate = local.scan_pdf(pdf_path, secondary=True, cyrillic=True)
    if [page['page'] for page in candidate['pages']] != [page['page'] for page in original['pages']]:
        raise RuntimeError('ollama_cyrillic_ocr_incomplete_pages')
    headings = [line for page in candidate['pages'] for line in local.role_headings(
        [line for line in candidate['lines'] if line['page'] == page['page']], page['width'])
        if local.CYRILLIC_ROLE_HEADING.fullmatch(line['text'])]
    receipt = {'model': material, 'seconds': candidate['seconds'],
               'selected': bool(headings), 'confirmed_heading_ids': [line['id'] for line in headings]}
    receipt['preserved_email_regions'] = local.preserves_email_regions(original, candidate)
    if not receipt['preserved_email_regions']:
        receipt['selected'] = False
        return original, receipt
    # In the classic form, a readable Box II/IV marker declares an applicant/
    # representative section. Never retain one role while losing the other:
    # that could let a mapper attach the second owner's email to the first.
    missing_roles = []
    for line in candidate['lines']:
        marker = re.fullmatch(r'Графа\s+(II|IV)\s*', line['text'], re.I)
        if not marker:
            continue
        pattern = (local.policy.APPLICANT_SECTION if marker[1].upper() == 'II'
                   else local.policy.AGENT_SECTION)
        if not any(heading['page'] == line['page'] and pattern.search(heading['text']) for heading in headings):
            missing_roles.append({'page': line['page'], 'box': marker[1].upper()})
    if missing_roles:
        receipt.update(selected=False, unconfirmed_declared_roles=missing_roles)
        return original, receipt
    if not headings:
        return original, receipt
    candidate['seconds'] = round(candidate['seconds'] + original['seconds'], 3)
    return candidate, receipt
