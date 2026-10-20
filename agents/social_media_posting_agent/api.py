"""Operator-only content controls; setup mode cannot arm public jobs."""
import asyncio
import logging
from typing import Literal
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .agent import run_agent
from .models import Settings
from .store import Store
from .tools import asset_path, media_path, media_digest, render_video
from .runtime import monitor, publish_due
from . import oauth
from .connectors import ProviderError
from .privacy import disconnect_youtube
from .public_pages import public_page

BASE='/api/agents/lexmom_marketing_agent/social'


def dashboard_data(settings=None):
    settings=settings or Settings.from_env();store=Store(settings.state_dir)
    rows=store.list();connections=store.metadata('connections')
    return {'drafts':[row.model_dump(mode='json') for row in rows],'publishing_enabled':settings.publishing_enabled,
        'connections':connections.get('platforms',{}),'checked_at':connections.get('checked_at'),
        'configured':{platform:settings.configured(platform) for platform in ('linkedin','youtube')},
        'apps_configured':{platform:settings.app_configured(platform) for platform in ('linkedin','youtube')},
        'connection_readiness':{'linkedin':{'available':settings.linkedin_product_approved,
            'reason':'' if settings.linkedin_product_approved else 'LinkedIn Community Management API approval is pending. Authorization will be available after LinkedIn approves the dedicated app.'},'youtube':{'available':True,'reason':''}},
        'connection_attempt':store.metadata('oauth_result'),
        'counts':{'drafts':sum(row.status=='draft' for row in rows),'approved':sum(row.status=='approved' for row in rows),
                  'published':sum(row.status=='published' for row in rows)},
        'metrics':{platform:connections.get('platforms',{}).get(platform,{}).get('metrics') for platform in ('linkedin','youtube')},
        'media_style':'Approved AI product illustrations; silent vertical promos. No recorded walkthrough is claimed.'}


class Edit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    title:str=Field(min_length=1,max_length=100)
    caption:str=Field(min_length=20,max_length=3000)
    privacy_status:Literal['private','unlisted','public']|None=None


def register_routes(app,authorize):
    @app.get(BASE+'/about')
    async def about():return public_page('about')

    @app.get(BASE+'/privacy')
    async def privacy_notice():return public_page('privacy')

    @app.middleware('http')
    async def no_social_cache(request,call_next):
        response=await call_next(request)
        if request.url.path.startswith(BASE+'/'):
            response.headers['Cache-Control']='private, no-store'
            response.headers['Referrer-Policy']='no-referrer'
        return response

    async def private(request,write=False):
        user=await authorize(request,write=write)
        if user.get('role') not in {'admin','operator'}:raise HTTPException(403,'An operator account is required')
        return user

    async def body(request):
        if len(await request.body())>8000:raise HTTPException(413,'Request too large')
        try:
            value=await request.json()
            if not isinstance(value,dict):raise ValueError()
            return value
        except ValueError:raise HTTPException(422,'A valid JSON request is required') from None

    @app.post(BASE+'/oauth/{platform}/begin')
    async def connect(platform:str,request:Request):
        user=await private(request,True)
        if await body(request):raise HTTPException(422,'Connection requests accept no credentials or overrides')
        try:
            url,binding=await asyncio.to_thread(oauth.begin,Settings.from_env(),platform,oauth.principal(user))
        except oauth.ApprovalPending as error:raise HTTPException(409,str(error)) from None
        except ValueError:raise HTTPException(409,'Dedicated application credentials and the exact LexMom destination must be configured first') from None
        response=JSONResponse({'authorization_url':url},headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
        response.set_cookie(oauth.COOKIE,binding,max_age=600,httponly=True,secure=True,samesite='lax',path=BASE+'/oauth/')
        return response

    @app.get(BASE+'/oauth/callback/{platform}')
    async def connected(platform:str,request:Request):
        user=await private(request)
        settings=Settings.from_env()
        try:
            record=await asyncio.to_thread(oauth.consume,settings,platform,request.query_params.get('state',''),
                request.cookies.get(oauth.COOKIE,''),oauth.principal(user))
            if request.query_params.get('error'):raise ValueError('Consent was declined')
            await asyncio.to_thread(oauth.complete,settings,platform,request.query_params.get('code',''),record)
            await asyncio.to_thread(monitor)
            outcome='connected'
        except (ValueError,ProviderError):
            outcome='connection-needs-attention'
        Store(settings.state_dir).metadata('oauth_result',{'platform':platform,'outcome':outcome,'checked_at':datetime.now(timezone.utc).isoformat()})
        response=RedirectResponse('/?social_connection='+outcome+'#lexmom/social_media_posting_agent',status_code=303,
            headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
        response.delete_cookie(oauth.COOKIE,path=BASE+'/oauth/',secure=True,httponly=True,samesite='lax')
        return response

    @app.get(BASE+'/data')
    async def data(request:Request):
        await private(request)
        return await asyncio.to_thread(dashboard_data)

    @app.post(BASE+'/prepare')
    async def prepare(request:Request):
        await private(request,True);payload=await body(request)
        try: result=await asyncio.to_thread(run_agent,payload)
        except ValidationError:raise HTTPException(422,'Only a bounded week number is accepted') from None
        if result['status']!='success':raise HTTPException(503,'Draft preparation failed validation; inspect the approved content and artwork')
        return {'status':result['status'],'drafts':len(result.get('data',{}).get('drafts',[])),'posts_published':0}

    @app.post(BASE+'/connections/check')
    async def check(request:Request):
        await private(request,True)
        if await body(request):raise HTTPException(422,'Connection checks accept no credentials or overrides')
        return await asyncio.to_thread(monitor)

    @app.post(BASE+'/youtube/disconnect')
    async def disconnect(request:Request):
        await private(request,True)
        if await body(request)!={'confirm':'disconnect-youtube-and-remove-data'}:
            raise HTTPException(422,'Confirm disconnecting YouTube and removing its stored API data')
        try:return await asyncio.to_thread(disconnect_youtube,Settings.from_env())
        except ProviderError:raise HTTPException(409,'Disconnect was not completed. Refresh the connection and retry; no YouTube videos were deleted.') from None

    @app.post(BASE+'/dispatch')
    async def dispatch(request:Request):
        await private(request,True)
        settings=Settings.from_env()
        if not settings.publishing_enabled:
            raise HTTPException(409,'Publishing is disabled; no content was uploaded or posted')
        if await body(request):raise HTTPException(422,'Dispatch accepts no credentials, content or configuration overrides')
        # The worker rechecks exact approvals/media/destination and claims each
        # due scheduled draft transactionally. It never publishes plain drafts.
        return await asyncio.to_thread(publish_due,settings)

    @app.post(BASE+'/{key}/edit')
    async def edit(key:str,request:Request):
        await private(request,True)
        try: payload=Edit.model_validate(await body(request))
        except ValidationError:raise HTTPException(422,'Valid title, caption and revision are required') from None
        def change(draft):
            draft.title=payload.title;draft.caption=payload.caption;draft.revision+=1
            if payload.privacy_status is not None:
                if draft.platform!='youtube':raise ValueError('Visibility applies only to YouTube')
                draft.privacy_status=payload.privacy_status
            draft.status='draft';draft.approval_digest=None;draft.scheduled_at=None;draft.destination_digest=None
            return draft
        try:return await asyncio.to_thread(Store(Settings.from_env().state_dir).update,key,payload.revision,change)
        except KeyError:raise HTTPException(404,'Draft not found') from None
        except ValueError:raise HTTPException(409,'Draft changed or requires reconciliation; refresh before editing') from None

    @app.post(BASE+'/{key}/render')
    async def render(key:str,request:Request):
        await private(request,True);payload=await body(request)
        if set(payload)!={'revision'} or isinstance(payload['revision'],bool) or not isinstance(payload['revision'],int):
            raise HTTPException(422,'The current draft revision is required')
        settings=Settings.from_env();store=Store(settings.state_dir)
        phase='draft'
        try:
            draft=store.get(key)
            if draft.revision!=payload['revision']:raise ValueError('Draft changed')
            if draft.status in {'publishing','processing','uploaded','published','needs_reconciliation'}:raise ValueError('Reconciliation required')
            phase='renderer'
            video=await asyncio.to_thread(render_video,draft,settings)
            def change(row):
                row.video=video;row.revision+=1;row.status='draft';row.approval_digest=None;row.scheduled_at=None;row.destination_digest=None
                return row
            phase='save'
            row=store.update(key,payload['revision'],change)
            return {'key':row.key,'revision':row.revision,'video_ready':True,'posts_published':0}
        except KeyError:raise HTTPException(404,'Draft not found') from None
        except ValueError as error:
            # Only fixed diagnostics may reach logs/UI; exception text can contain
            # untrusted data. Keep draft conflicts distinct from renderer failures.
            reasons={
                'Approved image is unavailable':'artwork-unavailable',
                'Unapproved image':'artwork-rejected',
                'Invalid video name':'filename-rejected',
                'Linked media paths are not permitted':'media-path-rejected',
                'Linked video is not permitted':'media-path-rejected',
                'Linked temporary video is not permitted':'media-path-rejected',
                'Video renderer unavailable or timed out; approved image remains available':'renderer-unavailable',
                'Video renderer did not produce a valid bounded output':'renderer-output-invalid',
            }
            reason=reasons.get(str(error),'validation-failed')
            logging.getLogger(__name__).warning('social_render_failed phase=%s reason=%s',phase,reason)
            if phase=='renderer':raise HTTPException(503,'Private video renderer needs attention ('+reason+'); the saved draft is preserved') from None
            raise HTTPException(409,'Draft changed or needs reconciliation; refresh before rendering') from None

    @app.post(BASE+'/{key}/approve')
    async def approve(key:str,request:Request):
        await private(request,True);payload=await body(request)
        if set(payload)!={'revision'} or isinstance(payload['revision'],bool) or not isinstance(payload['revision'],int):
            raise HTTPException(422,'The current draft revision is required')
        settings=Settings.from_env()
        def change(draft):
            draft.destination_digest=settings.destination_digest(draft.platform)
            draft.asset_digest=media_digest(draft,settings);draft.status='approved'
            draft.approval_digest=draft.digest();return draft
        try:
            draft=await asyncio.to_thread(Store(settings.state_dir).update,key,payload['revision'],change)
            return {'key':draft.key,'status':draft.status,'publishing_enabled':settings.publishing_enabled,'posts_published':0}
        except KeyError:raise HTTPException(404,'Draft not found') from None
        except ValueError:raise HTTPException(409,'Configure the destination, refresh the draft and render its video before approval') from None

    @app.post(BASE+'/{key}/pause')
    async def pause(key:str,request:Request):
        await private(request,True);payload=await body(request)
        if set(payload)!={'revision'} or type(payload['revision']) is not int:raise HTTPException(422,'The current draft revision is required')
        def change(draft):
            draft.status='paused';draft.revision+=1;draft.scheduled_at=None;draft.approval_digest=None
            return draft
        try:return await asyncio.to_thread(Store(Settings.from_env().state_dir).update,key,payload['revision'],change)
        except KeyError:raise HTTPException(404,'Draft not found') from None
        except ValueError:raise HTTPException(409,'Refresh the draft; an in-progress publication must be reconciled') from None

    @app.post(BASE+'/{key}/schedule')
    async def schedule(key:str,request:Request):
        await private(request,True)
        settings=Settings.from_env()
        if not settings.publishing_enabled:raise HTTPException(409,'Public scheduling is disabled during setup')
        payload=await body(request)
        if set(payload)!={'revision','scheduled_at'} or isinstance(payload['revision'],bool) or not isinstance(payload['revision'],int):
            raise HTTPException(422,'An approved draft revision and timezone-aware publishing time are required')
        try:
            moment=datetime.fromisoformat(payload['scheduled_at'].replace('Z','+00:00'))
            if moment.utcoffset() is None or moment<datetime.now(timezone.utc):raise ValueError()
            def change(draft):
                if draft.status!='approved' or draft.approval_digest!=draft.digest() or draft.asset_digest!=media_digest(draft,settings) or draft.destination_digest!=settings.destination_digest(draft.platform):
                    raise ValueError('Exact content/media approval required')
                draft.scheduled_at=moment.astimezone(timezone.utc);draft.approval_digest=draft.digest();draft.status='scheduled'
                return draft
            return await asyncio.to_thread(Store(settings.state_dir).update,key,payload['revision'],change)
        except (ValueError,TypeError,AttributeError,KeyError):raise HTTPException(409,'Review exact content, media and schedule before activation') from None

    @app.post(BASE+'/{key}/publish')
    async def publish(key:str,request:Request):
        await private(request,True)
        if not Settings.from_env().publishing_enabled:raise HTTPException(409,'Public posting and video uploads remain disabled')
        # Publication is always a durable scheduled action, never a direct UI retry.
        raise HTTPException(409,'Choose a publishing time for the approved draft; the supervised worker will execute it')

    @app.get(BASE+'/{key}/media')
    async def media(key:str,request:Request):
        await private(request)
        settings=Settings.from_env()
        try:
            draft=Store(settings.state_dir).get(key)
            path=media_path(settings,draft.video) if draft.platform=='youtube' and draft.video else asset_path(draft.image)
            if not path.is_file():raise ValueError()
            return FileResponse(path,headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
        except (KeyError,ValueError):raise HTTPException(404,'Media unavailable') from None
