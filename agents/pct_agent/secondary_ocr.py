"""Optional CPU OCR for scripts absent from Windows' installed OCR languages."""
import threading
import hashlib
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

_ENGINE=None
_LOCK=threading.Lock()


@lru_cache(maxsize=1)
def cache_material():
    import rapidocr
    models=Path(rapidocr.__file__).parent/'models'
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(models.glob('*.onnx'))}
    if len(files)<3:raise RuntimeError('ollama_secondary_ocr_models_missing')
    return {'rapidocr':version('rapidocr'),'onnxruntime':version('onnxruntime'),'models':files}


def recognize(image):
    global _ENGINE
    from rapidocr import RapidOCR
    with _LOCK:
        if _ENGINE is None:
            _ENGINE=RapidOCR(params={'Global.log_level':'error',
                'EngineConfig.onnxruntime.intra_op_num_threads':2,
                'EngineConfig.onnxruntime.inter_op_num_threads':1})
        result=_ENGINE(image)
    lines=[]
    if result.txts is None:return {'text':'','lines':[]}
    for box,text in zip(result.boxes,result.txts):
        xs=[float(p[0]) for p in box];ys=[float(p[1]) for p in box]
        lines.append({'text':text,'words':[{'text':text,'bounding_rect':{
            'x':min(xs),'y':min(ys),'width':max(xs)-min(xs),'height':max(ys)-min(ys)}}]})
    return {'text':'\n'.join(l['text'] for l in lines),'lines':lines}
