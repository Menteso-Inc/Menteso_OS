"""Authenticated campaign/mailbox endpoints; only approved artwork and opt-out are public."""
from __future__ import annotations

import asyncio
import html
import re
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from .agent import run_agent
from .models import Settings
from .store import Store
from .tools import load_campaigns, render_email, unsubscribe_address

BASE='/api/agents/lexmom_marketing_agent'
ASSETS=Path(__file__).resolve().parents[2]/'static/email-assets'


def dashboard_data(settings=None):
    settings=settings or Settings.from_env(); store=Store(settings.state_dir)
    campaigns=load_campaigns()
    snapshot=store.dashboard()
    snapshot['campaigns']=[campaign.model_dump() for campaign in campaigns]
    snapshot['previews']=[render_email(campaign,step,settings) for campaign in campaigns for step in campaign.steps]
    snapshot['subject_examples']=[{'product':campaign.product,'day':step.day,
        'named':render_email(campaign,step,settings,contact_name='John',firm_name='Example Law')['subject'],
        'firm':render_email(campaign,step,settings,firm_name='Example Law')['subject']}
        for campaign in campaigns for step in campaign.steps]
    paths=[ASSETS/image for campaign in campaigns for step in campaign.steps for image in (step.image,step.secondary_image) if image]
    snapshot['readiness']={'drafts_valid':len(snapshot['previews'])==15,'drafts_expected':15,
                           'artwork_available':sum(path.is_file() for path in paths),
                           'artwork_expected':len(paths),'image_free':all('<img' not in p['html'].lower() for p in snapshot['previews']),'gmail_credentials_present':settings.gmail_credentials_present,
                           'gmail_api_connected':snapshot['mailbox_status'].get('connected') is True,
                           'sending_disabled':True}
    snapshot['review']=store.metadata('internal_review',{'sent':False})
    snapshot['review']['matches_current_drafts']=snapshot['review'].get('campaign_versions')=={campaign.product:campaign.version for campaign in campaigns}
    snapshot['monitor']=store.metadata('monitor_status',{})
    snapshot['research_handoff']=store.metadata('research_handoff',{})
    snapshot['reply_notifications']={'mode':'polling','interval_seconds':settings.interval_seconds,
                                     'push_connected':False}
    return snapshot


def register_routes(app, authorize):
    async def private(request,write=False):
        user=await authorize(request,write=write)
        if user.get('role') not in {'admin','operator'}:
            raise HTTPException(403,'An operator account is required to access the Lexmom mailbox')
        return user

    @app.get(BASE+'/email/data')
    async def email_data(request:Request):
        await private(request)
        return await asyncio.to_thread(dashboard_data)

    @app.post(BASE+'/email/prepare')
    async def email_prepare(request:Request):
        await private(request,True)
        if await request.body() not in {b'',b'{}'}:
            raise HTTPException(422,'Draft generation uses saved campaign JSON; sending overrides are disabled')
        result=await asyncio.to_thread(run_agent)
        return {'status':result['status'],'drafts':len(result.get('data',{}).get('previews',[])),
                'emails_sent':0,'campaigns_enabled':False}

    @app.post(BASE+'/email/send')
    async def disabled_send(request:Request):
        await private(request,True)
        raise HTTPException(409,'Campaign sending remains disabled. Internal review does not activate prospect sending.')

    @app.post(BASE+'/email/confirm-interest')
    async def confirm_interest(request:Request):
        await private(request,True)
        if len(await request.body())>2048: raise HTTPException(413,'Request too large')
        try:
            payload=await request.json()
        except ValueError:
            raise HTTPException(422,'Select an actual lead reply and product') from None
        if not isinstance(payload,dict) or set(payload)!={'email','message_id','product'}:
            raise HTTPException(422,'Select an actual lead reply and product')
        try:
            await asyncio.to_thread(Store(Settings.from_env().state_dir).confirm_interest,**payload)
        except (ValueError,TypeError): raise HTTPException(422,'An actual lead reply is required') from None
        return {'confirmed':True,'emails_sent':0}

    @app.get(BASE+'/email/preview/{product}/{day}')
    async def preview(request:Request,product:str,day:int):
        await private(request)
        campaign=next((row for row in load_campaigns() if row.product==product),None)
        if campaign is None or not 1<=day<=5: raise HTTPException(404,'Draft not found')
        rendered=render_email(campaign,campaign.steps[day-1],Settings.from_env())
        return HTMLResponse(rendered['html'],headers={'Cache-Control':'private, no-store',
            'Content-Security-Policy':"default-src 'none'; img-src https://os.menteso.com; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"})

    @app.get(BASE+'/email-assets/{filename}')
    async def artwork(filename:str):
        # Email clients cannot present dashboard cookies. Only these generated public graphics are exposed.
        if filename!='lexmom-logo-v1.webp' and not re.fullmatch(r'lexmom-(manage|launch)-day0[1-7]-v3\.png',filename):
            raise HTTPException(404,'Artwork not found')
        path=ASSETS/filename
        if path.is_symlink() or not path.is_file(): raise HTTPException(404,'Artwork not found')
        return FileResponse(path,headers={'Cache-Control':'public, max-age=86400','X-Content-Type-Options':'nosniff'})

    @app.get(BASE+'/email/unsubscribe/{token}')
    async def optout_form(token:str):
        settings=Settings.from_env()
        try: unsubscribe_address(token,settings.unsubscribe_secret.get_secret_value())
        except (ValueError,TypeError,UnicodeError): raise HTTPException(404,'Link unavailable') from None
        # Link scanners perform GET. Suppression requires the signed POST, never a page view.
        return HTMLResponse('<html><body><h1>Stop LexMom emails</h1><form method="post"><button type="submit" name="List-Unsubscribe" value="One-Click">Unsubscribe</button></form></body></html>',
                            headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})

    @app.post(BASE+'/email/unsubscribe/{token}')
    async def optout(token:str,request:Request):
        if len(await request.body())>2048: raise HTTPException(413,'Request too large')
        settings=Settings.from_env()
        try: email=unsubscribe_address(token,settings.unsubscribe_secret.get_secret_value())
        except (ValueError,TypeError,UnicodeError): raise HTTPException(404,'Link unavailable') from None
        await asyncio.to_thread(Store(settings.state_dir).suppress,email,'Unsubscribed')
        return {'unsubscribed':True}
