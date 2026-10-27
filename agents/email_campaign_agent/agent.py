"""Email Campaign specialist: grounded drafts and private monitoring, paused by default."""
from __future__ import annotations

import json
import time
from pathlib import Path

from shared.research_runtime import ResearchSession, redact
from .models import Settings
from .store import Store
from .tools import load_campaigns, render_email
from .tests import tests

AGENT_CONFIG={'name':'Email Campaign','role':'Lexmom email campaign specialist','description':'Manage and Launch drafts, sent-mail/reply visibility and delivery monitoring.',
              'version':'0.2.0','status':'paused','requires_llm':False,'execution_enabled':False,'ui_type':'lexmom_email','hosted_on':'aws','sub_agents':[]}


def create_agent():
    """Optional CrewAI orchestration definition; construction never starts paid inference."""
    from crewai import Agent
    from shared.llm import create_crewai_llm
    from shared.memory import load_memory
    memory=load_memory('email_campaign_agent')
    return Agent(role='Lexmom Email Campaign specialist',goal='Prepare grounded product-specific email drafts and monitor approved delivery without activating paused campaigns',
                 backstory='Legal judgment remains human-led. Use approved product facts and sourced contacts only. Past strategies: '+json.dumps(memory.get('refined_prompts',{})),
                 allow_delegation=False,verbose=False,llm=create_crewai_llm('LEXMOM_EMAIL_AGENT'))


def run_agent(input_data=None,on_step=None,settings=None,session=None):
    started=time.monotonic(); settings=settings or Settings.from_env(); store=Store(settings.state_dir)
    session=session or ResearchSession('email_campaign_agent')
    session.load_memory(); strategy=session.best_strategy('campaign_drafts',default='standard')
    if input_data and input_data.get('send'):
        raise PermissionError('Campaign sending is disabled; draft generation cannot activate it')
    try:
        campaigns=load_campaigns(); store.install_campaigns(campaigns)
        previews=[]
        for campaign in campaigns:
            previews.extend(render_email(campaign,step,settings) for step in campaign.steps)
        result={'status':'success','campaigns_enabled':False,'emails_sent':0,
                'data':{'campaigns':[c.model_dump() for c in campaigns],'previews':previews},
                'execution_time':round(time.monotonic()-started,3)}
        result['tests']=tests.run(result)
        if not result['tests']['passed']: raise ValueError('Campaign self-validation failed')
        session.finish({'status':'success','drafts':len(previews),'tests':result['tests']},'success',strategy,
                       'Generated validated paused product drafts with zero provider inference.',result['execution_time'])
        if on_step: on_step({'type':'step','message':'Fifteen paused drafts prepared. No email sent.'})
        return result
    except (ValueError,OSError) as exc:
        message=redact(str(exc)); session.finish({'status':'failure','reason':message},'failure',strategy,
            'Draft configuration must be repaired; no send was attempted.',time.monotonic()-started)
        return {'status':'failure','campaigns_enabled':False,'emails_sent':0,'error':message}


if __name__=='__main__':
    from shared.config import PROJECT_ROOT
    result=run_agent()
    print(json.dumps({'status':result['status'],'campaigns_enabled':False,'emails_sent':0,
                      'drafts':len(result.get('data',{}).get('previews',[])),'tests':result.get('tests')},indent=2))
