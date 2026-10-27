"""Official, identity-checked APIs. Ambiguous writes are never blindly retried."""
import os
import re
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlsplit

import httpx
from dotenv import set_key, dotenv_values
from shared.research_runtime import _file_lock
from .models import PREFIX, YOUTUBE_SCOPES
from .tools import asset_path, media_path
from .store import Store


class ProviderError(RuntimeError):
    def __init__(self,message,status_code=None):
        super().__init__(message);self.status_code=status_code
class UncertainOutcome(ProviderError): pass
class AuthorizationRevoked(ProviderError): pass


def persist_private(settings, name, value):
    if not re.fullmatch(r'[A-Z0-9_]{1,160}',name) or not name.startswith(PREFIX):
        raise ValueError('Invalid private credential reference')
    with _file_lock(settings.env_file.with_suffix('.lock')):
        set_key(str(settings.env_file),name,str(value))
        if os.name!='nt': os.chmod(settings.env_file,0o600)
    return name


def persist_private_many(settings, values, expected):
    if not values or any(not re.fullmatch(r'[A-Z0-9_]{1,160}',name) or not name.startswith(PREFIX) for name in values):
        raise ValueError('Invalid private credential reference')
    with _file_lock(settings.env_file.with_suffix('.lock')):
        current=dotenv_values(settings.env_file)
        if any((current.get(name) or '')!=value for name,value in expected.items()):
            raise ProviderError('Account configuration changed during renewal; refresh the dashboard')
        owner=settings.env_file.stat()
        descriptor,path=tempfile.mkstemp(prefix='.lexmom-social-',suffix='.env',dir=settings.env_file.parent)
        try:
            with os.fdopen(descriptor,'w',encoding='utf-8',newline='') as stream:
                stream.write(settings.env_file.read_text(encoding='utf-8'))
            for name,value in values.items():set_key(path,name,str(value))
            if os.name!='nt':os.chown(path,owner.st_uid,owner.st_gid)
            os.replace(path,settings.env_file)
            if os.name!='nt':os.chmod(settings.env_file,0o600)
        finally:
            if os.path.exists(path):os.unlink(path)


def safe_upload_url(value, platform):
    parts=urlsplit(value)
    allowed={'youtube':{'www.googleapis.com','upload.youtube.com'},'linkedin':{'www.linkedin.com','api.linkedin.com'}}
    if parts.scheme!='https' or parts.hostname not in allowed[platform] or parts.username or parts.password or parts.port not in {None,443}:
        raise ProviderError('Provider upload destination failed validation')
    return value


class Official:
    def __init__(self,settings,client=None):
        self.settings=settings
        self.client=client or httpx.Client(timeout=httpx.Timeout(30,connect=10),trust_env=False,follow_redirects=False)
        self.owned=client is None

    def close(self):
        if self.owned:self.client.close()

    def request(self,method,url,**kwargs):
        host=urlsplit(url).hostname or ''
        provider='linkedin' if host=='linkedin.com' or host.endswith('.linkedin.com') else 'youtube' if host.endswith('.googleapis.com') or host=='upload.youtube.com' else None
        store=Store(self.settings.state_dir) if provider else None
        if store and store.metadata('api_backoff_'+provider).get('retry_at',0)>time.time():
            raise ProviderError('Provider rate limit cooldown is active; access is preserved',429)
        for attempt in range(3 if method=='GET' else 1):
            try: response=self.client.request(method,url,**kwargs)
            except httpx.TransportError:
                if method!='GET':raise UncertainOutcome('Provider write outcome is unknown; reconciliation is required') from None
                if attempt==2:raise ProviderError('Provider could not be reached after bounded reads') from None
                time.sleep(.25*(attempt+1));continue
            if response.status_code==429:
                retry=response.headers.get('retry-after','');seconds=3600
                try:seconds=int(retry) if retry.isdigit() else int(parsedate_to_datetime(retry).timestamp()-time.time())
                except (ValueError,TypeError,OverflowError):pass
                if store:store.metadata('api_backoff_'+provider,{'retry_at':int(time.time())+max(900,seconds)})
                raise ProviderError('Provider rate limit reached; requests paused without reconnecting',429)
            if method=='GET' and response.status_code in {500,502,503,504} and attempt<2:
                time.sleep(.25*(attempt+1));continue
            if response.status_code>=500 and method!='GET':raise UncertainOutcome('Provider write outcome is unknown; reconciliation is required')
            if not 200<=response.status_code<300:
                if host=='oauth2.googleapis.com' and urlsplit(url).path=='/token' and response.status_code==400:
                    try:revoked=response.json().get('error')=='invalid_grant'
                    except (ValueError,AttributeError):revoked=False
                    if revoked:raise AuthorizationRevoked('YouTube authorization was revoked or expired; reconnect to continue',400)
                raise ProviderError('Provider rejected the request; check authorization, quota and content',response.status_code)
            return response
        raise ProviderError('Provider read attempts exhausted')

    def require_publishing(self):
        if not self.settings.publishing_enabled:
            raise PermissionError('Public posting and uploads remain disabled')


class LinkedIn(Official):
    def _credential_snapshot(self):
        return {PREFIX+name.upper():getattr(self.settings,name).get_secret_value() for name in (
            'linkedin_client_id','linkedin_client_secret','linkedin_organization_urn','linkedin_access_token','linkedin_refresh_token')}

    def accept_token_response(self,response,refreshing=False):
        now=int(time.time());lifetime=response.get('expires_in');access=response.get('access_token')
        if not isinstance(access,str) or not 0<len(access)<=10000 or type(lifetime) is not int or not 0<lifetime<=366*86400:
            raise ProviderError('LinkedIn authorization expiry is invalid; credentials were not saved')
        refresh=response.get('refresh_token') or (self.settings.linkedin_refresh_token.get_secret_value() if refreshing else '')
        refresh_expiry=self.settings.linkedin_refresh_expires_at if refreshing else 0
        if refresh:
            if not isinstance(refresh,str) or len(refresh)>10000:raise ProviderError('LinkedIn refresh authorization is invalid')
            remaining=response.get('refresh_token_expires_in')
            if remaining is not None:
                if type(remaining) is not int or not 0<remaining<=366*86400:raise ProviderError('LinkedIn refresh expiry is invalid')
                refresh_expiry=min(now+remaining,refresh_expiry) if refreshing and refresh_expiry else now+remaining
            if refresh_expiry<=now:raise ProviderError('LinkedIn refresh expiry is unavailable; authorize again')
        updates={'linkedin_access_token':type(self.settings.linkedin_access_token)(access),'linkedin_expires_at':now+lifetime,
            'linkedin_refresh_token':type(self.settings.linkedin_refresh_token)(refresh),'linkedin_refresh_expires_at':refresh_expiry,
            'linkedin_refresh_retry_at':0,'linkedin_refresh_blocked':False}
        candidate=self.settings.model_copy(update=updates);adapter=LinkedIn(candidate,self.client);adapter._skip_renewal=True
        verified=adapter.verify()
        values={PREFIX+name.upper():(value.get_secret_value() if hasattr(value,'get_secret_value') else str(value).lower() if isinstance(value,bool) else value) for name,value in updates.items()}
        persist_private_many(self.settings,values,self._credential_snapshot())
        self.settings=candidate
        return verified

    def _renew_if_due(self):
        now=int(time.time());settings=self.settings
        if getattr(self,'_skip_renewal',False) or not settings.configured('linkedin') or not settings.linkedin_expires_at or settings.linkedin_expires_at>now+7*86400:
            return
        if not settings.linkedin_refresh_token.get_secret_value() or settings.linkedin_refresh_blocked or settings.linkedin_refresh_expires_at<=now or settings.linkedin_refresh_retry_at>now:
            return
        try:
            response=self.request('POST','https://www.linkedin.com/oauth/v2/accessToken',data={
                'grant_type':'refresh_token','refresh_token':settings.linkedin_refresh_token.get_secret_value(),
                'client_id':settings.linkedin_client_id.get_secret_value(),'client_secret':settings.linkedin_client_secret.get_secret_value()}).json()
            self.accept_token_response(response,refreshing=True)
        except (ProviderError,ValueError) as error:
            blocked=isinstance(error,ProviderError) and error.status_code in {400,401,403}
            persist_private_many(settings,{PREFIX+'LINKEDIN_REFRESH_RETRY_AT':now+6*3600,
                PREFIX+'LINKEDIN_REFRESH_BLOCKED':str(blocked).lower()},self._credential_snapshot())
            self.settings=settings.model_copy(update={'linkedin_refresh_retry_at':now+6*3600,'linkedin_refresh_blocked':blocked})

    def headers(self):
        return {'Authorization':'Bearer '+self.settings.linkedin_access_token.get_secret_value(),
            'Linkedin-Version':self.settings.linkedin_version,'X-Restli-Protocol-Version':'2.0.0'}

    def verify(self):
        self._renew_if_due()
        if not self.settings.configured('linkedin'):raise ProviderError('Dedicated Lexmom LinkedIn authorization is not configured')
        urn=self.settings.linkedin_organization_urn.get_secret_value()
        if not re.fullmatch(r'urn:li:organization:\d+',urn):raise ProviderError('Invalid configured LinkedIn destination')
        token=self.request('POST','https://www.linkedin.com/oauth/v2/introspectToken',data={
            'token':self.settings.linkedin_access_token.get_secret_value(),
            'client_id':self.settings.linkedin_client_id.get_secret_value(),
            'client_secret':self.settings.linkedin_client_secret.get_secret_value()}).json()
        scopes=token.get('scope',[])
        if isinstance(scopes,str): scopes=scopes.split()
        if token.get('active') is not True or 'w_organization_social' not in scopes or not {'r_organization_admin','rw_organization_admin'}.intersection(scopes):
            raise ProviderError('LinkedIn organization posting/admin-read permissions are missing or expired')
        found=False
        for start in range(0,500,100):
            data=self.request('GET','https://api.linkedin.com/rest/organizationAcls',headers=self.headers(),
                params={'q':'roleAssignee','state':'APPROVED','count':100,'start':start}).json()
            elements=data.get('elements',[])
            found=any((item.get('organization') or item.get('organizationTarget'))==urn and item.get('state')=='APPROVED'
                and item.get('role') in {'ADMINISTRATOR','CONTENT_ADMINISTRATOR','CONTENT_ADMIN'} for item in elements)
            if found or len(elements)<100:break
        if not found:raise ProviderError('The authorizing account has no verified Lexmom Page posting role')
        result={'connected':True,'destination':'LexMom','checked_at':datetime.now(timezone.utc).isoformat()}
        if self.settings.linkedin_expires_at:
            result['expires_at']=datetime.fromtimestamp(self.settings.linkedin_expires_at,timezone.utc).isoformat()
            result['renewal_required_soon']=self.settings.linkedin_expires_at<time.time()+7*86400
        automatic=bool(self.settings.linkedin_refresh_token.get_secret_value()) and self.settings.linkedin_refresh_expires_at>time.time() and not self.settings.linkedin_refresh_blocked
        result['renewal_mode']='automatic' if automatic else 'owner_reauthorization'
        if self.settings.linkedin_refresh_expires_at:
            result['refresh_expires_at']=datetime.fromtimestamp(self.settings.linkedin_refresh_expires_at,timezone.utc).isoformat()
        if self.settings.linkedin_refresh_blocked:
            result['reason']='Existing access checked; LinkedIn requires owner reauthorization before it expires.'
        elif self.settings.linkedin_refresh_retry_at>time.time():
            result['reason']='Existing access checked; token renewal is waiting for its bounded retry window.'
        elif result.get('renewal_required_soon') and not automatic:
            result['reason']='LinkedIn did not grant renewable access; reconnect before the displayed expiry.'
        return result

    def metrics(self, verified=False):
        if not verified:self.verify()
        data=self.request('GET','https://api.linkedin.com/rest/organizationalEntityShareStatistics',headers=self.headers(),
            params={'q':'organizationalEntity','organizationalEntity':self.settings.linkedin_organization_urn.get_secret_value()}).json()
        rows=data.get('elements')
        if not isinstance(rows,list):raise ProviderError('LinkedIn metrics response is incomplete')
        columns={'impressions':'impressionCount','clicks':'clickCount','likes':'likeCount','comments':'commentCount'}
        return {name:sum(item.get('totalShareStatistics',{}).get(field,0) for item in rows) for name,field in columns.items()}

    def publish(self,draft):
        self.require_publishing();self.verify()
        if draft.platform!='linkedin':raise ProviderError('Wrong platform adapter')
        owner=self.settings.linkedin_organization_urn.get_secret_value()
        initialization=self.request('POST','https://api.linkedin.com/rest/images?action=initializeUpload',headers=self.headers(),
            json={'initializeUploadRequest':{'owner':owner}}).json().get('value',{})
        upload=safe_upload_url(initialization.get('uploadUrl',''),'linkedin')
        image=initialization.get('image')
        if not isinstance(image,str) or not image.startswith('urn:li:image:'):raise ProviderError('LinkedIn asset response is incomplete')
        persist_private(self.settings,PREFIX+'ASSET_'+draft.key.replace('-','_').upper(),image)
        self.require_publishing()
        with asset_path(draft.image).open('rb') as stream:
            self.request('PUT',upload,headers={**self.headers(),'Content-Type':'image/png'},content=stream)
        ready=False
        for attempt in range(3):
            data=self.request('GET','https://api.linkedin.com/rest/images/'+quote(image,safe=''),headers=self.headers()).json()
            if data.get('status')=='AVAILABLE':ready=True;break
            time.sleep(.5*(attempt+1))
        if not ready:raise ProviderError('LinkedIn image is not available yet; public post was not submitted')
        self.require_publishing()
        response=self.request('POST','https://api.linkedin.com/rest/posts',headers=self.headers(),json={
            'author':owner,'commentary':draft.caption,'visibility':'PUBLIC','lifecycleState':'PUBLISHED',
            'distribution':{'feedDistribution':'MAIN_FEED','targetEntities':[],'thirdPartyDistributionChannels':[]},
            'content':{'media':{'id':image,'title':draft.title}},'isReshareDisabledByAuthor':False})
        identifier=response.headers.get('x-restli-id')
        if not identifier:raise UncertainOutcome('LinkedIn accepted a post without a usable receipt; reconcile it')
        return persist_private(self.settings,PREFIX+'RECEIPT_'+draft.key.replace('-','_').upper(),identifier)


class YouTube(Official):
    def headers(self):
        if not hasattr(self,'token'):
            if not self.settings.configured('youtube'):raise ProviderError('Dedicated Lexmom YouTube authorization is not configured')
            response=self.request('POST','https://oauth2.googleapis.com/token',data={
                'client_id':self.settings.google_client_id.get_secret_value(),
                'client_secret':self.settings.google_client_secret.get_secret_value(),
                'refresh_token':self.settings.google_refresh_token.get_secret_value(),'grant_type':'refresh_token'}).json()
            if not response.get('access_token'):
                raise ProviderError('YouTube token renewal requires authorization')
            scopes=response.get('scope')
            if not scopes:
                info=self.request('GET','https://oauth2.googleapis.com/tokeninfo',params={'access_token':response['access_token']}).json()
                if info.get('aud')!=self.settings.google_client_id.get_secret_value():
                    raise ProviderError('YouTube token belongs to another application')
                scopes=info.get('scope','')
            if not YOUTUBE_SCOPES.issubset(set(scopes.split())):
                raise ProviderError('Dedicated YouTube upload, channel-read and analytics permissions are required')
            self.token=response['access_token']
        return {'Authorization':'Bearer '+self.token}

    def verify(self):
        data=self.request('GET','https://www.googleapis.com/youtube/v3/channels',headers=self.headers(),params={'part':'id,snippet','mine':'true'}).json()
        rows=data.get('items',[])
        if len(rows)!=1 or rows[0].get('id')!=self.settings.youtube_channel_id.get_secret_value():
            raise ProviderError('Authorized YouTube channel is not the configured LexMom channel')
        return {'connected':True,'destination':'LexMom','checked_at':datetime.now(timezone.utc).isoformat()}

    def metrics(self, verified=False):
        if not verified:self.verify()
        today=datetime.now(timezone.utc).date()
        data=self.request('GET','https://youtubeanalytics.googleapis.com/v2/reports',headers=self.headers(),params={
            'ids':'channel==MINE','startDate':(today-timedelta(days=28)).isoformat(),'endDate':today.isoformat(),
            'metrics':'views,estimatedMinutesWatched,likes,comments,subscribersGained'}).json()
        names=[entry.get('name') for entry in data.get('columnHeaders',[])]
        rows=data.get('rows',[])
        return {name:sum(row[index] for row in rows) for index,name in enumerate(names)}

    def publish(self,draft):
        self.require_publishing();self.verify()
        if draft.platform!='youtube' or not draft.video:raise ProviderError('A rendered YouTube video is required')
        path=media_path(self.settings,draft.video)
        if not path.is_file() or not 0<path.stat().st_size<=50_000_000:raise ProviderError('Rendered video is unavailable or too large')
        response=self.request('POST','https://www.googleapis.com/upload/youtube/v3/videos',headers={**self.headers(),
            'X-Upload-Content-Type':'video/mp4','X-Upload-Content-Length':str(path.stat().st_size)},
            params={'uploadType':'resumable','part':'snippet,status','notifySubscribers':'false'},json={
                'snippet':{'title':draft.title,'description':draft.caption,'categoryId':'28','defaultLanguage':'en'},
                'status':{'privacyStatus':draft.privacy_status,'selfDeclaredMadeForKids':False,'containsSyntheticMedia':True}})
        upload=safe_upload_url(response.headers.get('location',''),'youtube')
        persist_private(self.settings,PREFIX+'UPLOAD_'+draft.key.replace('-','_').upper(),upload)
        self.require_publishing()
        with path.open('rb') as stream:
            result=self.request('PUT',upload,headers={**self.headers(),'Content-Type':'video/mp4','Content-Length':str(path.stat().st_size)},content=stream).json()
        if not result.get('id'):raise UncertainOutcome('YouTube upload receipt is unavailable; reconcile before any retry')
        receipt=persist_private(self.settings,PREFIX+'RECEIPT_'+draft.key.replace('-','_').upper(),result['id'])
        # Upload acceptance and video processing are separate observations.
        return receipt

    def processing_status(self,receipt_key,privacy_status='public'):
        self.verify()
        if not receipt_key or not receipt_key.startswith(PREFIX+'RECEIPT_'):raise ProviderError('Video receipt is unavailable')
        identifier=dotenv_values(self.settings.env_file).get(receipt_key,'')
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}',identifier):raise ProviderError('Video receipt is invalid')
        data=self.request('GET','https://www.googleapis.com/youtube/v3/videos',headers=self.headers(),
            params={'part':'snippet,status,processingDetails','id':identifier}).json()
        rows=data.get('items',[])
        if len(rows)!=1 or rows[0].get('snippet',{}).get('channelId')!=self.settings.youtube_channel_id.get_secret_value():
            raise ProviderError('Video receipt does not match the Lexmom channel')
        row=rows[0];status=row.get('status',{});processing=row.get('processingDetails',{}).get('processingStatus')
        if status.get('uploadStatus') in {'failed','rejected','deleted'} or processing in {'failed','terminated'}:return 'failed'
        if status.get('uploadStatus')=='processed' and processing=='succeeded':
            if status.get('privacyStatus')!=privacy_status:return 'needs_reconciliation'
            return 'published' if privacy_status=='public' else 'uploaded'
        return 'processing'
