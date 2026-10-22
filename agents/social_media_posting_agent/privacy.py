"""Explicit YouTube revocation and removal. Never invoked by setup or a status check."""
import httpx
from dotenv import dotenv_values
from shared.research_runtime import _file_lock
from .connectors import ProviderError, persist_private_many
from .models import PREFIX
from .store import Store


def clear_youtube_authorized_data(settings):
    """Caller holds worker.lock; a changed account must never be cleared by an older worker."""
    expected={PREFIX+name.upper():getattr(settings,name).get_secret_value() for name in (
        'google_client_id','google_client_secret','google_refresh_token','youtube_channel_id')}
    store=Store(settings.state_dir)
    values={PREFIX+'GOOGLE_REFRESH_TOKEN':'',PREFIX+'OAUTH_PENDING_YOUTUBE':''}
    current=dotenv_values(settings.env_file)
    for row in store.list():
        if row.platform!='youtube':continue
        for kind in ('UPLOAD_','RECEIPT_'):
            key=PREFIX+kind+row.key.replace('-','_').upper()
            if key in current:values[key]=''
    persist_private_many(settings,values,expected)
    store.purge_youtube_authorized_data()


def disconnect_youtube(settings,client=None):
    """Revoke only the configured grant, then remove its live provider data. Authored drafts survive."""
    with _file_lock(settings.state_dir/'worker.lock'):
        current=dotenv_values(settings.env_file)
        names=('google_client_id','google_client_secret','google_refresh_token','youtube_channel_id')
        if any((current.get(PREFIX+name.upper()) or '')!=getattr(settings,name).get_secret_value() for name in names):
            raise ProviderError('Account configuration changed; refresh before disconnecting')
        token=settings.google_refresh_token.get_secret_value()
        owned=client is None;client=client or httpx.Client(timeout=30,trust_env=False,follow_redirects=False)
        try:
            if token:
                try:response=client.post('https://oauth2.googleapis.com/revoke',data={'token':token})
                except httpx.TransportError:raise ProviderError('Google revocation could not be confirmed; retry disconnect from the dashboard') from None
                already_revoked=False
                if response.status_code==400:
                    try:already_revoked=response.json().get('error')=='invalid_token'
                    except (ValueError,AttributeError):pass
                if response.status_code!=200 and not already_revoked:
                    raise ProviderError('Google revocation was not accepted; the saved connection was preserved')
            clear_youtube_authorized_data(settings)
        finally:
            if owned:client.close()
    return {'disconnected':True,'youtube_data_removed':True,'authored_drafts_preserved':True,'youtube_videos_deleted':0}
