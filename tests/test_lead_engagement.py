"""Real event-to-contact association and honest lead-temperature transitions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.email_campaign_agent.engagement import lead_table
from agents.email_campaign_agent.store import Store, now


class LeadEngagementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name))
        self.email='jane@example.org'
        self.store.save_contact(self.email,{'product':'manage'},['Sending off'])
        self.key=self.store.prepare(self.email,'manage',1,'v1',now(),{})
        self.store.outcome(self.key,'sent',provider_id='test-provider')
        self.firm={'provenance':'live','domain':'example.org','name':'Example Law','fit_status':'needs_research',
            'primary_product':'none','contacts':[{'email':self.email,'name':'Jane Doe','role':'Partner','research_ready':False}]}

    def table(self): return lead_table([self.firm],self.store.engagement_activity())

    def event(self,kind,**payload):
        document={'eventType':kind,'mail':{'messageId':'test-provider'},kind.lower():{'timestamp':now(),**payload}}
        self.store.ingest_event(document);return document

    def test_total_counts_contacts_once_not_firms_or_duplicate_runs(self):
        other={**self.firm,'contacts':[{'email':self.email.upper()},{'email':'info@example.org'}]}
        data=lead_table([self.firm,other,{'provenance':'fixture','contacts':[{'email':'fake@example.org'}]}],{})
        self.assertEqual(data['total'],2)
        self.assertEqual(data['rows'][0]['temperature'],'new')
        self.assertFalse(data['campaigns_enabled'])

    def test_ready_counts_and_details_preserve_this_contacts_evidence(self):
        person={'field':'contact_role','value':'Partner','source_url':'https://example.org/jane',
                'excerpt':'Jane Doe, Partner, jane@example.org'}
        other={'field':'email','value':'other@example.org','source_url':'https://example.org/other','excerpt':'Other person'}
        self.firm.update(countries=['GB','US'],size=8,size_basis='published_roster',
                         evidence=[{'field':'practice_area','value':str(i)} for i in range(80)]+[other])
        self.firm['contacts'][0].update(research_ready=True,verification_status='valid',verification_provider='hunter',evidence=[person])
        table=self.table();row=table['rows'][0]
        self.assertEqual((table['qualified_verified'],table['held']),(1,0))
        self.assertEqual(row['country'],'GB, US')
        self.assertEqual(row['verification_provider'],'hunter')
        self.assertEqual(row['size_basis'],'published_roster')
        self.assertIn(person,row['evidence'])
        self.assertNotIn(other,row['evidence'])
        self.assertEqual(row['temperature'],'new')

    def test_open_is_not_hot_or_warm_and_duplicate_event_is_not_recounted(self):
        event=self.event('Open',isBotEvent='Unlikely')
        self.assertFalse(self.store.ingest_event(event))
        row=self.table()['rows'][0]
        self.assertEqual(row['temperature'],'opened');self.assertEqual(row['activity']['opens'],1)
        self.assertFalse(row['research_ready'])

    def test_only_product_cta_click_can_make_a_lead_warm(self):
        self.event('Click',link='https://os.menteso.com/email/unsubscribe/test')
        self.assertEqual(self.table()['rows'][0]['temperature'],'new')
        self.event('Click',link='https://lexmom.com/launch/')
        self.assertEqual(self.table()['rows'][0]['temperature'],'new')
        self.event('Click',link='https://lexmom.com/manage/?utm_source=email',isBotEvent='Unlikely')
        self.assertEqual(self.table()['rows'][0]['temperature'],'warm')
        self.assertFalse(self.table()['rows'][0]['research_ready'])

    def test_likely_bot_events_do_not_heat_a_lead(self):
        self.event('Open',isBotEvent='Likely')
        self.event('Click',isBotEvent='Likely',link='https://lexmom.com/manage/')
        self.assertEqual(self.table()['rows'][0]['temperature'],'new')

    def test_combined_sequence_recognizes_either_product_without_restarting(self):
        key=self.store.prepare(self.email,'both',1,'v1',now(),{})
        self.store.outcome(key,'sent',provider_id='combined-provider')
        for product,link in (('launch','https://lexmom.com/launch/'),
                             ('manage','https://lexmom.com/manage/book-demo?utm_source=email')):
            self.store.ingest_event({'eventType':'Click','mail':{'messageId':'combined-provider'},
                'click':{'timestamp':now(),'link':link,'isBotEvent':'Unlikely'}})
        self.assertEqual(self.table()['rows'][0]['activity']['clicks'],2)
        self.assertEqual(self.table()['rows'][0]['temperature'],'warm')
        with self.store.connection() as db:
            details=[json.loads(r[0]) for r in db.execute('SELECT detail FROM events')]
            self.assertEqual({d.get('clicked_product') for d in details},{'launch','manage'})
            self.assertEqual(db.execute('SELECT COUNT(*) FROM actions').fetchone()[0],2)

    def test_similar_paths_untrusted_origins_and_userinfo_are_not_product_clicks(self):
        for link in ('https://lexmom.com/manage-other/','https://lexmom.com:444/manage/',
                     'https://user@lexmom.com/manage/','https://lexmom.com.evil.example/manage/',
                     'http://lexmom.com/manage/'):
            self.event('Click',link=link,isBotEvent='Unlikely')
        self.assertEqual(self.table()['rows'][0]['temperature'],'new')
        self.assertEqual(self.table()['rows'][0]['activity']['clicks'],0)

    def test_orphan_event_and_wrong_recipient_tag_do_not_heat_any_contact(self):
        self.store.ingest_event({'eventType':'Click','click':{'link':'https://lexmom.com/manage/'},
            'mail':{'messageId':'other-provider','tags':{'lexmom-action':[self.key]},'destination':['other@example.org']}})
        self.assertEqual(self.table()['rows'][0]['temperature'],'new')

    def test_unreviewed_reply_is_not_hot_and_confirmation_needs_actual_sender(self):
        reply={'message_id':'real-reply','thread_id':'thread','direction':'incoming','sender_email':self.email,
            'subject':'Interested in a demo','body':'Please show me Manage','labels':['INBOX']}
        self.store.save_mail(reply)
        self.assertEqual(self.table()['rows'][0]['temperature'],'replied')
        with self.assertRaises(ValueError):self.store.confirm_interest('other@example.org','real-reply','manage')
        self.store.confirm_interest(self.email,'real-reply','manage')
        self.assertEqual(self.table()['rows'][0]['temperature'],'hot')
        self.assertFalse(self.table()['campaigns_enabled'])

    def test_spam_automated_and_outbound_messages_cannot_confirm_interest(self):
        for extra in ({'labels':['SPAM']},{'is_automated':True},{'direction':'sent'}):
            reply={'message_id':'unqualified-reply','thread_id':'thread','direction':'incoming','sender_email':self.email,
                'subject':'Demo','labels':['INBOX'],**extra}
            self.store.save_mail(reply)
            with self.assertRaises(ValueError):self.store.confirm_interest(self.email,'unqualified-reply','manage')

    def test_suppression_overrides_prior_click_and_interest(self):
        self.event('Click',link='https://lexmom.com/manage/')
        self.store.suppress(self.email,'Unsubscribed')
        self.assertEqual(self.table()['rows'][0]['temperature'],'suppressed')
        self.assertEqual(self.table()['warm'],0)

    def test_unavailable_activity_is_unknown_instead_of_fabricated_zero_interest(self):
        table=lead_table([self.firm],{},available=False)
        self.assertEqual(table['rows'][0]['temperature'],'unknown')
        self.assertFalse(table['activity_available'])

    def test_event_storage_omits_personal_ip_user_agent_and_raw_link(self):
        self.event('Click',link='https://lexmom.com/manage/?private_token=example',ipAddress='198.51.100.5',userAgent='Private client')
        with self.store.connection() as db: value=db.execute('SELECT detail FROM events').fetchone()[0]
        self.assertNotIn('198.51.100.5',value);self.assertNotIn('Private client',value);self.assertNotIn('private_token',value)

    def test_reply_time_uses_mail_arrival_and_is_not_advanced_by_sync(self):
        reply={'message_id':'old-reply','direction':'incoming','sender_email':self.email,
               'labels':['INBOX'],'received_at_ms':'1704067200000'}
        self.store.save_mail(reply)
        before=self.table()['rows'][0]['activity']['last_activity_at']
        self.assertEqual(before,'2024-01-01T00:00:00+00:00')
        with patch('agents.email_campaign_agent.store.now',return_value='2026-10-14T12:00:00+00:00'):
            self.store.save_mail({**reply,'labels':['INBOX','IMPORTANT']})
        self.assertEqual(self.table()['rows'][0]['activity']['last_activity_at'],before)

    def test_reply_without_provider_time_keeps_first_observation(self):
        reply={'message_id':'no-date','direction':'incoming','sender_email':self.email,'labels':['INBOX']}
        with patch('agents.email_campaign_agent.store.now',return_value='2026-10-13T12:00:00+00:00'):
            self.store.save_mail(reply)
        with patch('agents.email_campaign_agent.store.now',return_value='2026-10-14T12:00:00+00:00'):
            self.store.save_mail(reply)
        self.assertEqual(self.table()['rows'][0]['activity']['last_activity_at'],'2026-10-13T12:00:00+00:00')


if __name__=='__main__': unittest.main()
