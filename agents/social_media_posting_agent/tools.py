"""Content generation from approved product facts, with zero provider calls."""
import hashlib
import json
import logging
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from .models import Draft

ASSETS=Path(__file__).resolve().parents[2]/'static/email-assets'
CONTENT=Path(__file__).with_name('content.json')


def asset_path(filename):
    if not re.fullmatch(r'lexmom-(manage|launch)-day0[1-7]-v3\.png',filename): raise ValueError('Unapproved image')
    path=ASSETS/filename
    if ASSETS.is_symlink() or path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=8_000_000:
        raise ValueError('Approved image is unavailable')
    return path


def media_path(settings, filename):
    if not re.fullmatch(r'[a-z0-9-]{1,80}\.mp4',filename): raise ValueError('Invalid video name')
    folder=settings.state_dir/'media'
    if settings.state_dir.is_symlink() or folder.is_symlink(): raise ValueError('Linked media paths are not permitted')
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/filename
    if path.is_symlink(): raise ValueError('Linked video is not permitted')
    return path


def media_digest(draft, settings):
    path=media_path(settings,draft.video) if draft.platform=='youtube' and draft.video else asset_path(draft.image)
    if draft.platform=='youtube' and not draft.video: raise ValueError('Render the video before approving it')
    if not path.is_file() or not 0<path.stat().st_size<=50_000_000: raise ValueError('Media file is unavailable or too large')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(65536),b''): digest.update(chunk)
    return digest.hexdigest()


def load_drafts(week=1, strategy='standard'):
    if isinstance(week,bool) or not isinstance(week,int) or not 1<=week<=52: raise ValueError('Week must be between 1 and 52')
    payload=json.loads(CONTENT.read_text(encoding='utf-8'))
    if payload.get('publishing_enabled') is not False: raise ValueError('Saved content policy must remain setup-only')
    drafts=[]
    for row in payload['drafts']:
        draft=Draft.model_validate({**row,'key':row['key'].replace('week1-',f'week{week}-'),
            'caption':row['caption'].replace('_week1',f'_week{week}')})
        for url in re.findall(r'https?://\S+',draft.caption):
            parsed=urlsplit(url)
            if parsed.scheme!='https' or parsed.hostname!='lexmom.com' or not parsed.path.startswith('/'+draft.product):
                raise ValueError('Content links must match the approved product')
        try: asset_path(draft.image)
        except ValueError:
            if strategy=='available_assets_only': continue
            raise
        drafts.append(draft)
    if not drafts: raise ValueError('No validated content is available')
    return drafts


def render_video(draft, settings):
    """Render a real silent vertical promo from approved AI campaign artwork.

    No image-generation, voice-generation, browser or external API is called.
    The exact artwork is preserved within a padded frame, with fade motion.
    """
    from shared.research_runtime import _file_lock
    with _file_lock(settings.state_dir/('render-'+draft.key+'.lock')):
        return _render_video(draft,settings)


def _render_video(draft, settings):
    if draft.platform!='youtube': raise ValueError('Only YouTube drafts need a video')
    import imageio_ffmpeg
    executable=imageio_ffmpeg.get_ffmpeg_exe()
    source=asset_path(draft.image)
    # A draft revision/approval does not change these pixels. Reuse only an
    # exact artwork/style render, independent of the previous video filename.
    render_digest=hashlib.sha256(source.read_bytes()+b'lexmom-vertical-1080x1920-12s-v1').hexdigest()
    target=media_path(settings,draft.key[:50]+'-'+render_digest[:16]+'.mp4')
    if target.is_file() and 0<target.stat().st_size<=50_000_000:return target.name
    temporary=target.with_name(target.stem+'-rendering.mp4')
    if temporary.is_symlink(): raise ValueError('Linked temporary video is not permitted')
    command=[executable,'-nostdin','-hide_banner','-loglevel','error','-y','-filter_threads','1','-filter_complex_threads','1',
        '-threads','1','-thread_queue_size','1','-framerate','25','-loop','1','-i',str(source),
        '-vf','scale=1080:-2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0xeeeafb,fade=t=in:st=0:d=0.6,fade=t=out:st=11:d=1,format=yuv420p',
        '-t','12','-r','25','-an','-c:v','libx264','-preset','fast','-threads','2','-movflags','+faststart',str(temporary)]
    try:
        result=subprocess.run(command,capture_output=True,timeout=150)
    except (OSError,subprocess.TimeoutExpired):
        temporary.unlink(missing_ok=True)
        raise ValueError('Video renderer unavailable or timed out; approved image remains available') from None
    if result.returncode or not temporary.is_file() or not 0<temporary.stat().st_size<=50_000_000:
        temporary.unlink(missing_ok=True)
        # The command has only fixed flags and approved local artwork. Redact
        # file references before retaining its bounded codec/resource diagnostic.
        diagnostic=result.stderr.decode(errors='replace') if isinstance(result.stderr,bytes) else str(result.stderr or '')
        diagnostic=re.sub(r'(?:https?|file)://\S+|/\S+','[local-reference]',diagnostic[-1200:])
        logging.getLogger(__name__).warning('social_ffmpeg_exit=%s diagnostic=%s',result.returncode,diagnostic)
        raise ValueError('Video renderer did not produce a valid bounded output')
    temporary.replace(target)
    return target.name


def prepare_content_tool():
    from langchain_core.tools import tool
    @tool
    def prepare_social_week(week:int=1)->str:
        """Prepare grounded private LinkedIn and YouTube drafts. Never publish."""
        return json.dumps([draft.model_dump(mode='json') for draft in load_drafts(week)])
    return prepare_social_week
