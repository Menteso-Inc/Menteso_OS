"""Dedicated, cookie-bound OAuth consent. No upload or publication occurs here."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

from dotenv import dotenv_values, set_key
from shared.research_runtime import _file_lock
from .connectors import Official, ProviderError, LinkedIn, YouTube, persist_private
from .models import PREFIX, YOUTUBE_SCOPES

CALLBACK_BASE='https://os.menteso.com/api/agents/lexmom_marketing_agent/social/oauth/callback/'
LINKEDIN_SCOPES=frozenset({'w_organization_social','rw_organization_admin','r_organization_social'})
COOKIE='__Secure-lexmom-social-oauth'


class ApprovalPending(ValueError):pass


def principal(user):
    identity={key:user[key] for key in ('id','username','email') if user.get(key)}
    if not identity:raise ValueError('A stable signed-in operator identity is required')
    return json.dumps(identity,sort_keys=True)


def begin(settings, platform, session_cookie):
    if platform not in {'linkedin','youtube'} or not settings.app_configured(platform):
        raise ValueError('Configure the dedicated app and LexMom destination before connecting')
    if platform=='linkedin' and not settings.linkedin_product_approved:
        raise ApprovalPending('LinkedIn Community Management API review is in progress. Connect after LinkedIn approves the dedicated app.')
    if not session_cookie:raise ValueError('A signed-in dashboard session is required')
    state=secrets.token_urlsafe(32);binding=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
    record={'state':hashlib.sha256(state.encode()).hexdigest(),'binding':hashlib.sha256(binding.encode()).hexdigest(),
        'session':hashlib.sha256(session_cookie.encode()).hexdigest(),'created':time.time(),'verifier':verifier,
        'destination':settings.destination_digest(platform)}
    persist_private(settings,PREFIX+'OAUTH_PENDING_'+platform.upper(),json.dumps(record))
    params={'response_type':'code','redirect_uri':CALLBACK_BASE+platform,'state':state}
    if platform=='youtube':
        params.update(client_id=settings.google_client_id.get_secret_value(),scope=' '.join(sorted(YOUTUBE_SCOPES)),
            access_type='offline',prompt='consent select_account',include_granted_scopes='false',
            code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),
            code_challenge_method='S256')
        endpoint='https://accounts.google.com/o/oauth2/v2/auth'
    else:
        params.update(client_id=settings.linkedin_client_id.get_secret_value(),scope=' '.join(sorted(LINKEDIN_SCOPES)))
        endpoint='https://www.linkedin.com/oauth/v2/authorization'
    return endpoint+'?'+urlencode(params),binding


def consume(settings, platform, state, binding, session_cookie):
    if platform not in {'youtube','linkedin'}:raise ValueError('Unknown social platform')
    if not all(isinstance(v,str) and 0<len(v)<=10000 for v in (state,binding,session_cookie)):
        raise ValueError('Authorization session is incomplete; connect again')
    key=PREFIX+'OAUTH_PENDING_'+platform.upper()
    with _file_lock(settings.env_file.with_suffix('.lock')):
        try:record=json.loads(dotenv_values(settings.env_file).get(key) or '{}')
        except ValueError:raise ValueError('Connect again from the dashboard') from None
        age=time.time()-record.get('created',0)
        expected={'state':state,'binding':binding,'session':session_cookie}
        if not 0<=age<=600 or record.get('destination')!=settings.destination_digest(platform) or any(not hmac.compare_digest(record.get(k,''),hashlib.sha256(v.encode()).hexdigest()) for k,v in expected.items()):
            raise ValueError('Authorization expired or belongs to a different browser session')
        set_key(str(settings.env_file),key,'')
    return record


def complete(settings, platform, code, record):
    if platform not in {'youtube','linkedin'}:raise ValueError('Unknown social platform')
    if not isinstance(code,str) or not 0<len(code)<=10000:raise ValueError('Authorization code is missing')
    transport=Official(settings)
    try:
        if platform=='youtube':
            response=transport.request('POST','https://oauth2.googleapis.com/token',data={
                'grant_type':'authorization_code','code':code,'redirect_uri':CALLBACK_BASE+platform,
                'client_id':settings.google_client_id.get_secret_value(),'client_secret':settings.google_client_secret.get_secret_value(),
                'code_verifier':record['verifier']}).json()
            if not response.get('refresh_token') or not YOUTUBE_SCOPES.issubset(set(response.get('scope','').split())):
                raise ProviderError('YouTube offline consent or requested permissions were not granted')
            candidate=settings.model_copy(update={'google_refresh_token':type(settings.google_refresh_token)(response['refresh_token'])})
            adapter=YouTube(candidate)
            try:verified=adapter.verify()
            finally:adapter.close()
            persist_private(settings,PREFIX+'GOOGLE_REFRESH_TOKEN',response['refresh_token'])
        else:
            response=transport.request('POST','https://www.linkedin.com/oauth/v2/accessToken',data={
                'grant_type':'authorization_code','code':code,'redirect_uri':CALLBACK_BASE+platform,
                'client_id':settings.linkedin_client_id.get_secret_value(),'client_secret':settings.linkedin_client_secret.get_secret_value()}).json()
            adapter=LinkedIn(settings)
            try:verified=adapter.accept_token_response(response)
            finally:adapter.close()
        return verified
    finally:transport.close()
