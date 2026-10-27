"""Contact counts and observed engagement; research fit is a separate decision."""
from collections import Counter


def lead_table(records, activity, *, available=True):
    leads={}
    for firm in records:
        if firm.get('provenance')!='live': continue
        for contact in firm.get('contacts',[]):
            email=str(contact.get('email') or '').strip().casefold()
            if not email: continue
            row=activity.get(email,{})
            temperature=('unknown' if not available else 'suppressed' if row.get('suppressed') else
                'hot' if row.get('confirmed_interest') else 'warm' if row.get('clicks',0)>0 else
                'replied' if row.get('replies',0)>0 else 'opened' if row.get('opens',0)>0 else 'new')
            proposed={'email':email,'name':contact.get('name'),'role':contact.get('role'),
                'firm':firm.get('name') or firm.get('domain'),'website':firm.get('website'),
                'country':', '.join(firm.get('countries') or []) or firm.get('country'),'size':firm.get('size'),'size_basis':firm.get('size_basis','unknown'),'product':firm.get('primary_product') or 'none',
                'qualification':firm.get('fit_status'),'research_ready':contact.get('research_ready') is True,
                'verification':contact.get('verification_status'),'verified_at':contact.get('verified_at'),
                'verification_provider':contact.get('verification_provider'),
                'temperature':temperature,'activity':{'opens':row.get('opens',0),'clicks':row.get('clicks',0),'replies':row.get('replies',0),
                    'last_activity_at':row.get('last_activity_at')},'hold_reasons':contact.get('readiness_reasons',[]),
                'evidence':list({(e.get('field'),e.get('value'),e.get('source_url'),e.get('excerpt')):e
                    for e in [*contact.get('evidence',[]),*firm.get('evidence',[])]
                    if e.get('field') not in {'email','contact_name','contact_role'} or e in contact.get('evidence',[])}.values())[:60],
                'product_assessments':firm.get('product_assessments',{})}
            previous=leads.get(email)
            if not previous or (proposed['research_ready'],bool(proposed['name']))>(previous['research_ready'],bool(previous['name'])):
                leads[email]=proposed
    rows=sorted(leads.values(),key=lambda row:({'hot':0,'warm':1,'replied':2,'opened':3}.get(row['temperature'],4),row['email']))
    counts=Counter(row['temperature'] for row in rows)
    ready=sum(row['research_ready'] for row in rows)
    return {'rows':rows,'total':len(rows),'qualified_verified':ready,'held':len(rows)-ready,
            'warm':counts['warm'],'hot':counts['hot'],'activity_available':available,
            'rules':{'new':'No recorded activity','opened':'Recorded open; privacy-proxy/scanner activity is possible',
                'warm':'A tracked click on the appropriate Lexmom product link','replied':'Reply received; interest requires review',
                'hot':'An operator confirmed an interested reply or demo request','suppressed':'Contact is suppressed; do not send'},
            'campaigns_enabled':False}
