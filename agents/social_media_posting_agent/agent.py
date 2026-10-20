"""Social Media Posting specialist: separate content preparation from publication."""
import json
import time

from pydantic import BaseModel, ConfigDict, Field
from shared.research_runtime import ResearchSession
from .models import Settings
from .store import Store
from .tools import load_drafts, prepare_content_tool
from .tests import tests

AGENT_CONFIG={'name':'Social Media Posting','role':'Lexmom social content specialist',
    'description':'Branded Manage/Launch content, calendar, official LinkedIn and YouTube integration.',
    'version':'0.2.0','status':'setup','requires_llm':False,'execution_enabled':True,
    'hidden_from_dashboard':True,'parent_agent':'lexmom_marketing_agent','hosted_on':'aws'}


def create_agent():
    from crewai import Agent
    from shared.llm import create_crewai_llm
    from shared.memory import load_memory
    memory=load_memory('social_media_posting_agent')
    return Agent(role='Lexmom Social Media Posting specialist',
        goal='Create grounded product-specific social content and operate only explicitly approved publications',
        backstory='Use LexMom approved branding and actual product facts. Private drafts are separate from publication. Past strategies: '+json.dumps(memory.get('refined_prompts',{})),
        llm=create_crewai_llm('LEXMOM_SOCIAL_AGENT'),allow_delegation=False,verbose=False)


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')
    week:int=Field(default=1,ge=1,le=52,strict=True)


def run_agent(input_data=None,on_step=None,settings=None,session=None):
    request=Input.model_validate(input_data or {})
    settings=settings or Settings.from_env();store=Store(settings.state_dir)
    session=session or ResearchSession('social_media_posting_agent')
    started=time.monotonic(); session.load_memory()
    preferred=session.best_strategy('social_drafts','standard')
    strategies=list(dict.fromkeys([preferred,'asset_first','available_assets_only']))[:3]
    failures=[]
    for strategy in strategies:
        try:
            drafts=load_drafts(request.week,strategy);store.install(drafts)
            result={'status':'success','publishing_enabled':False,'posts_published':0,
                'data':{'drafts':[draft.model_dump(mode='json') for draft in drafts]},'attempts':len(failures)+1}
            result['tests']=tests.run(result)
            if not result['tests']['passed']:raise ValueError('Content self-tests failed')
            session.finish({'drafts':len(drafts),'tests':result['tests'],'posts_published':0},'success',strategy,
                'Approved factual templates and media checks require no provider inference or publication.',time.monotonic()-started)
            if on_step:on_step({'type':'step','message':f'{len(drafts)} social drafts prepared; public posting remains off.'})
            return result
        except (ValueError,OSError,KeyError) as exc:
            failures.append({'strategy':strategy,'error_type':type(exc).__name__})
    session.finish({'status':'failure','attempts':failures},'failure',strategies[-1],
        'Content or approved media needs repair; no publication attempted.',time.monotonic()-started)
    return {'status':'failure','publishing_enabled':False,'posts_published':0,'errors':failures}


if __name__=='__main__':
    result=run_agent();print(json.dumps({'status':result['status'],'drafts':len(result.get('data',{}).get('drafts',[])),
        'posts_published':0,'publishing_enabled':False,'tests':result.get('tests')}))
