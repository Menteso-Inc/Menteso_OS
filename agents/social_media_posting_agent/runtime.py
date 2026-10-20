"""A supervised worker can monitor during setup; publication requires all gates."""
from datetime import datetime, timezone

from shared.research_runtime import _file_lock
from .connectors import LinkedIn, YouTube, ProviderError, UncertainOutcome, AuthorizationRevoked
from .models import Settings
from .store import Store
from .tools import media_digest


def monitor(settings=None):
    supplied=settings is not None;settings=settings or Settings.from_env()
    with _file_lock(settings.state_dir/'worker.lock'):
        if not supplied:settings=Settings.from_env()
        return _monitor(settings)


def _monitor(settings):
    store=Store(settings.state_dir);youtube_revoked=False
    result={'checked_at':datetime.now(timezone.utc).isoformat(),'publishing_enabled':settings.publishing_enabled,'platforms':{}}
    for platform,kind in [('linkedin',LinkedIn),('youtube',YouTube)]:
        if not settings.configured(platform):
            result['platforms'][platform]={'connected':False,'reason':'Dedicated API authorization is not configured'};continue
        adapter=kind(settings)
        try:
            result['platforms'][platform]=adapter.verify()
            try:
                result['platforms'][platform]['metrics']=adapter.metrics(verified=True)
            except ProviderError:
                result['platforms'][platform]['metrics_reason']='Analytics unavailable; account identity is verified'
        except AuthorizationRevoked as exc:
            from .privacy import clear_youtube_authorized_data
            clear_youtube_authorized_data(settings);youtube_revoked=True
            result['platforms'][platform]={'connected':False,'reason':str(exc)}
        except ProviderError as exc:
            result['platforms'][platform]={'connected':False,'reason':str(exc)}
        finally:adapter.close()
    store.metadata('connections',result)
    if settings.configured('youtube') and not youtube_revoked:
        adapter=YouTube(settings)
        try:
            for draft in store.list():
                if draft.platform=='youtube' and draft.status=='processing':
                    status=adapter.processing_status(draft.receipt_key,draft.privacy_status)
                    store.finish(draft.key,status,'Video processing/visibility checked',draft.receipt_key)
        except ProviderError:
            store.metadata('processing_blocker',{'reason':'Video processing could not be checked; retained for reconciliation','checked_at':result['checked_at']})
        finally:adapter.close()
    return result


def publish_due(settings=None):
    settings=settings or Settings.from_env();store=Store(settings.state_dir)
    if not settings.publishing_enabled:return {'posts_published':0,'publishing_enabled':False}
    published=0
    with _file_lock(settings.state_dir/'worker.lock'):
        store.recover_interrupted()
        for draft in store.list():
            if draft.status!='scheduled' or not draft.scheduled_at or draft.scheduled_at>datetime.now(timezone.utc):continue
            adapter=LinkedIn(settings) if draft.platform=='linkedin' else YouTube(settings)
            claimed=False
            try:
                if draft.asset_digest!=media_digest(draft,settings):raise ValueError('Approved media changed; review it again')
                if draft.destination_digest!=settings.destination_digest(draft.platform):raise ValueError('Destination changed; review it again')
                adapter.verify()
                draft=store.claim(draft.key,settings.daily_cap);claimed=True
                receipt=adapter.publish(draft)
                status='processing' if draft.platform=='youtube' else 'published'
                store.finish(draft.key,status,'Provider accepted the request; YouTube visibility is pending processing',receipt)
                if status=='published':published+=1
            except UncertainOutcome:
                if claimed:store.finish(draft.key,'needs_reconciliation','Provider outcome is uncertain; no automatic repeat')
            except (ValueError,ProviderError):
                if claimed:store.finish(draft.key,'failed','Publication was rejected; inspect connection/content before another reviewed draft')
                else:store.metadata('last_blocker',{'platform':draft.platform,'reason':'Destination, quota or media approval needs attention'})
            finally:adapter.close()
    return {'posts_published':published,'publishing_enabled':True}
