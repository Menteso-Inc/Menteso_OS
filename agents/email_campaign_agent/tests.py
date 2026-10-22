from shared.self_test import SelfTest

tests=SelfTest(agent_name='email_campaign_agent',validations=[
    {'name':'three_routes','check':lambda r: {c['product'] for c in r.get('data',{}).get('campaigns',[])}=={'manage','launch','both'},'message':'All three campaign routes are required'},
    {'name':'five_ordered_drafts','check':lambda r: len(r.get('data',{}).get('previews',[]))==15 and all([s['day'] for s in c['steps']]==list(range(1,6)) for c in r.get('data',{}).get('campaigns',[])),'message':'Each route needs five drafts'},
    {'name':'sending_disabled','check':lambda r: r.get('campaigns_enabled') is False and r.get('emails_sent')==0,'message':'Draft task must not send'},
    {'name':'image_free','check':lambda r: all('<img' not in p['html'].lower() for p in r.get('data',{}).get('previews',[])),'message':'Drafts must contain no images'},
    {'name':'paused_definitions','check':lambda r: all(c['status'] in {'draft','paused'} for c in r.get('data',{}).get('campaigns',[])),'message':'Draft task must not arm campaigns'},
])
