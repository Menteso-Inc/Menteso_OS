"""Grounded draft rendering and signed opt-out links, with no provider calls."""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

from shared.lexmom_email_transport import address
from .models import Campaign

ROOT = Path(__file__).resolve().parents[2]
ASSET_BASE = '/api/agents/lexmom_marketing_agent/email-assets/'


def load_campaigns():
    documents=json.loads(Path(__file__).with_name('campaigns.json').read_text(encoding='utf-8'))
    campaigns=[Campaign.model_validate(document) for document in documents]
    if len(campaigns)!=3 or {campaign.product for campaign in campaigns}!={'manage','launch','both'}:
        raise ValueError('Launch, Manage and combined campaign definitions are required')
    return campaigns


def unsubscribe_token(email, secret):
    if len(secret)<32: raise ValueError('Unsubscribe signing configuration is missing')
    value=address(email).lower().encode()
    encoded=base64.urlsafe_b64encode(value).decode().rstrip('=')
    signature=hmac.new(secret.encode(),encoded.encode(),hashlib.sha256).hexdigest()
    return encoded+'.'+signature


def unsubscribe_address(token, secret):
    if len(secret)<32 or not isinstance(token,str) or len(token)>600:
        raise ValueError('Invalid unsubscribe link')
    encoded,signature=token.rsplit('.',1)
    expected=hmac.new(secret.encode(),encoded.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected): raise ValueError('Invalid unsubscribe link')
    return address(base64.urlsafe_b64decode(encoded+'='*((-len(encoded))%4)).decode()).lower()


def render_email(campaign, step, settings, *, contact_name=None, firm_name=None, sourced_intro=None, email=None):
    recipient=address(email) if email else None
    def name(value,limit):
        if value is None:return ''
        value=str(value).strip()
        if any(char in value for char in '\r\n\x00'):
            raise ValueError('Names cannot contain email header controls')
        return value[:limit]
    person=name(contact_name,50);firm=name(firm_name,60)
    template=step.subject_named if person and step.subject_named else step.subject_firm if firm and step.subject_firm else None
    subject=(template.format(contact_name=person,firm_name=firm or 'your firm') if template else step.subject)[:150]
    greeting='Hi'+(' '+person if person else ' '+firm+' team' if firm else '')+','
    sections=[greeting]
    if sourced_intro: sections.append(str(sourced_intro).strip()[:240])
    copy=step.body_firm if firm and not person and step.body_firm else step.body
    if firm and not person and step.day==1 and not step.body_firm:
        responsibility={'launch':'your firm’s website and client intake','manage':'your firm’s matter workflows','both':'your firm’s website or practice operations'}[campaign.product]
        copy='Who looks after '+responsibility+'? Please share this with the appropriate colleague if that is someone else.\n\n'+copy
    sections.append(copy.format(firm_name=firm or 'your firm'))
    sections.append(campaign.cta_label+': '+campaign.cta_url)
    if campaign.secondary_cta_url:
        sections.append(campaign.secondary_cta_label+': '+campaign.secondary_cta_url)
    sections.append('Regards, Sherry | LexMom team\nsupport@lexmom.com')
    optout='Reply “stop” if you do not want further emails.'
    link=None
    if recipient and settings.unsubscribe_secret.get_secret_value():
        link=settings.public_origin+'/api/agents/lexmom_marketing_agent/email/unsubscribe/'+unsubscribe_token(recipient,settings.unsubscribe_secret.get_secret_value())
        optout+='\nUnsubscribe: '+link
    sections.append(optout)
    if settings.postal_address: sections.append(settings.postal_address)
    text='\n\n'.join(sections)
    esc=html.escape
    content_sections=sections[:3 if sourced_intro else 2]
    paragraphs=''.join('<p>'+esc(part).replace('\n','<br>')+'</p>' for part in content_sections)
    ctas=[(campaign.cta_label,campaign.cta_url)]
    if campaign.secondary_cta_url:ctas.append((campaign.secondary_cta_label,campaign.secondary_cta_url))
    links='<p>'+'<br>'.join('<a href="'+esc(url)+'">'+esc(label)+'</a>' for label,url in ctas)+'</p>'
    footer='<p style="font-size:12px;color:#555">Reply “stop” if you do not want further emails.'
    if link:footer+='<br><a href="'+esc(link)+'">Unsubscribe</a>'
    if settings.postal_address:footer+='<br>'+esc(settings.postal_address)
    footer+='</p>'
    body='<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:16px;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.6;color:#202124"><div style="max-width:640px">'+paragraphs+links+'<p>Regards, Sherry | LexMom team<br><a href="mailto:support@lexmom.com">support@lexmom.com</a></p>'+footer+'</div></body></html>'
    return {'subject':subject,'text':text,'html':body,'image':step.image,'secondary_image':step.secondary_image,
            'day':step.day,'kind':step.kind,'offset_days':step.offset_days,'references_step':step.references_step,
            'new_information':step.new_information,'product':campaign.product,'unsubscribe_url':link}


def mime_message(rendered, *, sender, recipient, reply_to, action_key):
    # The archive has a stable RFC ID, allowing insertion reconciliation after a lost response.
    message=EmailMessage()
    message['From']='LexMom <'+address(sender)+'>'
    message['To']=address(recipient); message['Reply-To']=address(reply_to)
    message['Subject']=rendered['subject']; message['Date']=formatdate(localtime=False,usegmt=True)
    message['Message-ID']='<lexmom-'+action_key+'@meetlexmom.com>'
    message['X-Lexmom-Action']=action_key
    if rendered.get('unsubscribe_url'):
        message['List-Unsubscribe']='<'+rendered['unsubscribe_url']+'>'
        message['List-Unsubscribe-Post']='List-Unsubscribe=One-Click'
    message.set_content(rendered['text']); message.add_alternative(rendered['html'],subtype='html')
    return message.as_bytes()


def review_bundle(settings):
    campaigns=load_campaigns()
    esc=html.escape; blocks=[]; texts=[]
    strategy=(
        'INTERNAL REVIEW ONLY — nothing is scheduled or enrolled.\n\n'
        'Audience: sourced law-firm owners, partners and operations contacts, plus relevant general firm inboxes. '
        'Launch: firms with a supported website need. Manage: firms with a supported case-workflow need. '
        'Both: evidence supports both needs and no product preference is known. Never assume an old workflow or a missing website without evidence.\n\n'
        'One contact gets one sequence, with at most five emails total: introduction, three follow-ups and final feedback. '
        'Proposed spacing: days 1, 3, 6, 10 and 14, during the recipient’s weekday business hours. '
        'These are proposed offsets, not an active sending schedule. Personalize with a sourced name, firm and one relevant fact.\n\n'
        'Follow-ups are one continuing conversation: recall the immediately preceding email, add a useful point and ask one clear question. '
        'Before dispatch, require confirmed provider acceptance of that prior step in the same product/version. Never claim the recipient opened, read or replied without evidence.\n\n'
        'Response strategy for later activation: no response → next planned step; opens alone → no escalation; '
        'a credible Launch/Manage link click → focus the remaining unsent steps on that product without restarting or adding emails; '
        'any real reply → pause automated follow-ups for review; interested reply/demo request → human demo handoff; '
        'signup → stop acquisition and hand off to onboarding; confirmed purchase → stop all acquisition; '
        'unsubscribe, complaint or hard bounce → suppress immediately; final feedback/no response → close this sequence without automatic recycling.\n\n'
        'Activation is deferred. Real signup/demo/payment hooks and automatic product-branch scheduling still need integration after the Lexmom product work. '
        'Current mailbox monitoring and suppression remain enabled; prospect sending remains disabled. '
        'Before activation: validate audience eligibility, postal identity, opt-out, fresh verification and sender limits.\n\n'
        'Deliverability: use authenticated SES, one recipient per message and small initial batches. '
        'Opens can be inflated by privacy proxies and clicks by security scanners. Delivery does not reveal Inbox versus Spam. '
        'Measure controlled seed placement, bounces, complaints, replies and confirmed conversions; never promise zero spam.\n\n'
        'Review requested: approve audience fit, truthful personalization, product claims, cadence and final-feedback language. '
        'Approval of this review does not activate campaigns.'
    )
    for campaign in campaigns:
        intro=f'LexMom {campaign.product.title()} — five drafts; campaign remains paused.'
        texts.append(intro)
        blocks.append(f'<h2 style="color:#472ed1">{esc(intro)}</h2>')
        for step in campaign.steps:
            preview=render_email(campaign,step,settings)
            named=render_email(campaign,step,settings,contact_name='John',firm_name='Example Law')['subject']
            firm=render_email(campaign,step,settings,firm_name='Example Law')['subject']
            heading=f'Email {step.day} / proposed day {step.offset_days+1}: {step.kind.replace("_"," ").title()}'
            texts.append(f'{heading}\nSubject: {step.subject}\nNamed-contact example: {named}\nFirm-inbox example: {firm}\nReferences: '+(f'email {step.references_step}' if step.references_step else 'no earlier email')+f'\nNew information/purpose: {step.new_information}\n\n{preview["text"]}')
            links='<a href="'+settings.public_origin+'/api/agents/lexmom_marketing_agent/email/preview/'+campaign.product+'/'+str(step.day)+'">Complete text-only preview</a>'
            blocks.append(f'<h3>{esc(heading)}</h3><p><strong>{esc(step.subject)}</strong></p><p style="font-size:13px">Named-contact example: {esc(named)}<br>Firm-inbox example: {esc(firm)}</p><p>{links}</p><p style="white-space:pre-line;line-height:1.6">{esc(preview["text"])}</p>')
    text=strategy+'\n\n'+'\n\n-----\n\n'.join(texts)
    body='<html><body style="font-family:Arial,Helvetica,sans-serif;color:#1c1b1f;max-width:680px;margin:24px auto;padding:20px"><h1>LexMom five-email campaign review</h1><p style="white-space:pre-line;line-height:1.65">'+esc(strategy)+'</p>'+''.join(blocks)+'</body></html>'
    versions={campaign.product:campaign.version for campaign in campaigns}
    digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
    return {'subject':'LexMom five-email strategy — Launch, Manage and both','text':text,'html':body,
            'campaigns':[campaign.model_dump() for campaign in campaigns],'campaign_versions':versions,'digest':digest}
