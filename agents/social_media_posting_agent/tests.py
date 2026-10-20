from shared.self_test import SelfTest
from .models import Draft


def valid(result):
    rows=result.get('data',{}).get('drafts',[])
    return bool(rows) and all(Draft.model_validate(row).status in {'draft','approved','paused'} for row in rows)


tests=SelfTest(agent_name='social_media_posting_agent',validations=[
    {'name':'validated_content','check':valid,'message':'No valid setup-only drafts'},
    {'name':'unique_content','check':lambda r:len({p['key'] for p in r['data']['drafts']})==len(r['data']['drafts']),'message':'Duplicate content keys'},
    {'name':'no_publication','check':lambda r:r.get('posts_published')==0 and r.get('publishing_enabled') is False,'message':'Draft preparation must not publish'},
])
