"""Delivery safety and authenticated mailbox boundaries, without network calls."""
import base64
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agents.email_campaign_agent import api
from agents.email_campaign_agent.models import Campaign, Consent, Settings
from agents.email_campaign_agent.runtime import collect_prospects, collect_saved_prospects, enroll, monitor_once, send_reserved
from agents.email_campaign_agent.store import Store, now
from agents.email_campaign_agent.tools import load_campaigns, render_email, review_bundle, unsubscribe_token
from shared.lexmom_gmail import Gmail, HistoryExpired, MailboxError, normalize_message


class EmailBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(state_dir=self.root, unsubscribe_secret='x'*40)
        self.store = Store(self.root)

    def prepare(self, day=1, email='lead@example.org', product='manage', due=None):
        key = self.store.prepare(email, product, day, 'v1', due or now(), {'subject':'Hello','html':'<p>Hello</p>','text':'Hello'})
        with self.store.connection(write=True) as db:
            db.execute("UPDATE actions SET status='queued' WHERE action_key=?", (key,))
        return key


class CampaignSafetyTests(EmailBase):
    def test_three_routes_have_exactly_five_stages_and_reject_legacy_seven(self):
        campaigns=load_campaigns()
        self.assertEqual({c.product for c in campaigns},{'launch','manage','both'})
        for campaign in campaigns:
            self.assertEqual([s.kind for s in campaign.steps],['introduction','follow_up_1','follow_up_2','follow_up_3','feedback'])
            bad=campaign.model_dump();bad['steps'].extend([bad['steps'][-1]]*2)
            with self.assertRaises(ValidationError):Campaign.model_validate(bad)

    def test_combined_text_draft_has_both_links_and_five_actions(self):
        campaign=next(c for c in load_campaigns() if c.product=='both')
        rendered=render_email(campaign,campaign.steps[0],self.settings)
        for url in ('https://lexmom.com/launch/','https://lexmom.com/manage/book-demo'):
            self.assertIn(url,rendered['text']);self.assertIn(url,rendered['html'])
        self.assertNotIn('<img',rendered['html'])
        consent={'email':'lead@example.org','product':'both','source':'Requested both product introduction','recorded_at':now(),'series_permitted':True,'timezone':'UTC'}
        keys=enroll(self.store,self.settings,consent,{'product':'both','research_ready':True})
        self.assertEqual(len(keys),5)
        self.assertEqual({self.store.action(k)['product'] for k in keys},{'both'})
        self.assertTrue(all(self.store.action(k)['status']=='prepared' for k in keys))

    def test_replacing_templates_cancels_old_unsent_but_preserves_accepted_history(self):
        old=self.prepare(day=7);accepted=self.prepare(day=1)
        self.store.outcome(accepted,'delivered',provider_id='historical')
        self.store.install_campaigns(load_campaigns())
        self.assertEqual(self.store.action(old)['status'],'cancelled')
        self.assertEqual(self.store.action(accepted)['status'],'delivered')
        self.assertEqual(self.store.action(accepted)['provider_id'],'historical')

    def test_combined_review_contains_all_fifteen_drafts_strategy_and_no_active_schedule(self):
        review=review_bundle(self.settings)
        self.assertEqual(len(review['campaigns']),3)
        self.assertEqual(sum(len(c['steps']) for c in review['campaigns']),15)
        self.assertIn('Activation is deferred',review['text'])
        self.assertIn('without restarting',review['text'])
        self.assertIn('stop all acquisition',review['text'])
        self.assertLess(len(review['html'].encode('utf-8')),100000)
        for c in review['campaigns']:
            for s in c['steps']:self.assertIn(s['subject'],review['text'])

    def test_subject_and_body_follow_named_or_firm_context_without_fake_names(self):
        launch=next(c for c in load_campaigns() if c.product=='launch');step=launch.steps[0]
        named=render_email(launch,step,self.settings,contact_name='John',firm_name='Example Law')
        generic=render_email(launch,step,self.settings,firm_name='Example Law')
        fallback=render_email(launch,step,self.settings)
        self.assertEqual(named['subject'],'John, a website from one practice brief?')
        self.assertEqual(generic['subject'],'Example Law: an AI website from a short brief?')
        self.assertIn('Example Law team',generic['text']);self.assertIn('Hi John,',named['text'])
        self.assertEqual(fallback['subject'],step.subject)
        self.assertNotIn('{contact_name}',named['subject']);self.assertNotIn('John',fallback['text'])
        self.assertNotIn('we created',named['text'].lower())

    def test_every_draft_is_short_personalized_and_image_free_with_safe_fallbacks(self):
        for campaign in load_campaigns():
            for step in campaign.steps:
                self.assertLessEqual(len(step.body.split()),65)
                for person in ('John',None):
                    rendered=render_email(campaign,step,self.settings,contact_name=person,firm_name='Example Law')
                    self.assertIn('Example Law',rendered['text'])
                    self.assertNotIn('{firm_name}',rendered['text'])
                    self.assertNotIn('{contact_name}',rendered['text'])
                    self.assertNotIn('<img',rendered['html'].lower())
                    self.assertNotIn('email-assets',rendered['html'])
                fallback=render_email(campaign,step,self.settings)
                self.assertIn('your firm',fallback['text'])
                self.assertNotIn('John',fallback['text'])
        self.assertNotIn('<img',review_bundle(self.settings)['html'])

    def test_body_templates_cannot_evaluate_attributes_or_unknown_facts(self):
        campaign=load_campaigns()[0]
        for field in ('body','body_firm'):
            for token in ('{firm_name.__class__}','{firm_name!r}','{firm_name:>1000}','{sourced_fact}'):
                bad=campaign.model_dump();bad['steps'][0][field]='A message containing '+token
                with self.assertRaises(ValidationError):Campaign.model_validate(bad)
        rendered=render_email(campaign,campaign.steps[0],self.settings,firm_name='<script>Firm</script>',sourced_intro='Public <img src=x> statement')
        self.assertIn('&lt;script&gt;',rendered['html'])
        self.assertNotIn('<img',rendered['html'])

    def test_followups_reference_the_immediately_preceding_step_and_have_new_value(self):
        for campaign in load_campaigns():
            self.assertEqual([s.references_step for s in campaign.steps],[None,1,2,3,4])
            self.assertTrue(all(s.new_information for s in campaign.steps))
            wrong=campaign.model_dump();wrong['steps'][2]['references_step']=1
            with self.assertRaises(ValidationError):Campaign.model_validate(wrong)
            missing=campaign.model_dump();missing['steps'][2]['new_information']=None
            with self.assertRaises(ValidationError):Campaign.model_validate(missing)

    def test_followup_reservation_requires_confirmed_prior_send_in_the_same_series(self):
        second=self.prepare(day=2);intro=self.prepare(day=1)
        self.assertFalse(self.store.prior_send_accepted(second))
        self.assertIsNone(self.store.reserve(second,10))
        self.store.outcome(intro,'unknown')
        self.assertIsNone(self.store.reserve(second,10))
        self.store.outcome(intro,'sent',provider_id='accepted-prior')
        self.assertTrue(self.store.prior_send_accepted(second))
        self.assertIsNotNone(self.store.reserve(second,10))

    def test_other_product_or_template_version_cannot_be_used_as_previous_context(self):
        intro=self.prepare(product='manage');second=self.prepare(day=2,product='both')
        self.store.outcome(intro,'delivered',provider_id='another-product')
        self.assertFalse(self.store.prior_send_accepted(second))
        same_product=self.prepare(product='both')
        self.store.outcome(same_product,'delivered',provider_id='old-version')
        with self.store.connection(write=True) as database:
            database.execute("UPDATE actions SET version='older' WHERE action_key=?",(same_product,))
        self.assertIsNone(self.store.reserve(second,10))

    def test_subject_personalization_rejects_header_injection_and_unsupported_templates(self):
        campaign=load_campaigns()[0]
        for name in ('John\r\nBcc: hidden@example.org','Firm\x00Name'):
            with self.assertRaises(ValueError):render_email(campaign,campaign.steps[0],self.settings,contact_name=name)
        for field,value in (('subject_named','{contact_name.__class__}'),('subject_named','{contact_name!r}'),
                            ('subject_named','{contact_name:>1000}'),('subject_firm','{contact_name}, hi')):
            bad=campaign.model_dump();bad['steps'][0][field]=value
            with self.assertRaises(ValidationError):Campaign.model_validate(bad)

    def test_personalized_subject_unicode_survives_mime_archival(self):
        from email import policy
        from email.parser import BytesParser
        from agents.email_campaign_agent.tools import mime_message
        campaign=load_campaigns()[0]
        rendered=render_email(campaign,campaign.steps[0],self.settings,contact_name='João')
        raw=mime_message(rendered,sender='hello@meetlexmom.com',recipient='lead@example.org',
                         reply_to='support@lexmom.com',action_key='test')
        message=BytesParser(policy=policy.default).parsebytes(raw)
        self.assertEqual(str(message['Subject']),rendered['subject'])
        self.assertIn('João',message.get_body(preferencelist=('plain',)).get_content())

    def test_research_handoff_uses_sourced_excerpt_and_keeps_daily_permission_hold(self):
        firm={'firm_id':'f','website':'https://example.org','domain':'example.org','name':'Example Firm',
              'fit_status':'qualified','fit_reasons':['Sourced law firm'],'product':'lexmom_manage',
              'researched_at':now(),'provenance':'live','primary_product':'manage','qualification_policy_version':'v1',
              'product_assessments':{'manage':{'status':'potential_fit'}},
              'contacts':[{'email':'lead@example.org','name':'Owner','inbox_type':'named','research_ready':True,'verified_at':now()}],
              'personalization_briefs':[{'product':'manage','email':'lead@example.org','audience':'named',
                  'product_policy_version':'v1','question':'Could this help your team?',
                  'facts':[{'field':'practice_area','value':'Legal practice','source_url':'https://example.org',
                            'excerpt':'We support family law matters.'}]}]}
        self.assertEqual(collect_prospects([firm],self.store),1)
        contact=self.store.contact('lead@example.org')
        self.assertIn('We support family law matters.',contact['data']['sourced_intro'])
        self.assertTrue(any('permission' in reason for reason in contact['hold_reasons']))
        with patch('agents.lexmom_marketing_agent.agent.get_dashboard_data',return_value={'prospectInventory':[firm]}):
            self.assertEqual(collect_saved_prospects(self.store),1)
        self.assertEqual(self.store.dashboard()['actions'],[])

    def test_reply_tasks_are_durable_deduplicated_and_never_send(self):
        self.store.save_contact('lead@example.org',{'product':'manage'},[])
        message={'message_id':'reply','thread_id':'t','direction':'incoming','sender_email':'lead@example.org',
                 'subject':'Manage demo request','labels':['INBOX']}
        self.store.save_mail(message);self.store.save_mail(message)
        tasks=self.store.reply_tasks()
        self.assertEqual(len(tasks),1);self.assertEqual(tasks[0]['kind'],'demo_request')
        self.assertEqual(tasks[0]['outbound_status'],'held')
        self.assertTrue(tasks[0]['untrusted_content']);self.assertEqual(self.store.dashboard()['actions'],[])
        self.store.save_mail({**message,'message_id':'spam','labels':['SPAM']})
        self.store.save_mail({**message,'message_id':'unrelated','sender_email':'unknown@example.org','subject':'Hello'})
        self.assertEqual(len(self.store.reply_tasks()),1)

    def test_old_database_migrates_without_losing_actions(self):
        other=self.root/'old'; other.mkdir()
        db=sqlite3.connect(other/'email.sqlite3')
        db.execute('CREATE TABLE actions(action_key TEXT PRIMARY KEY,email TEXT,product TEXT,day INTEGER,version TEXT,due_at TEXT,status TEXT,document TEXT,provider_id TEXT,gmail_id TEXT,error TEXT,updated TEXT,UNIQUE(email,product,day))')
        db.execute('INSERT INTO actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', ('old','a@example.org','manage',1,'v1',now(),'unknown','{}',None,None,'Uncertain',now()))
        db.commit(); db.close()
        migrated=Store(other)
        self.assertEqual(migrated.action('old')['status'],'unknown')
        self.assertIn('dispatch_at',migrated.action('old'))

    def test_reservations_are_durable_and_daily_cap_uses_dispatch_date(self):
        moment=datetime.now(timezone.utc)-timedelta(minutes=5)
        one=self.prepare(email='one@example.org',due=(moment-timedelta(seconds=1)).isoformat())
        two=self.prepare(email='two@example.org',due=(moment-timedelta(seconds=1)).isoformat())
        self.assertIsNotNone(self.store.reserve(one,1,current=moment.isoformat()))
        self.store.outcome(one,'unknown')
        self.assertIsNone(self.store.reserve(one,10,current=now()))
        self.assertIsNone(self.store.reserve(two,1,current=now()))
        self.assertEqual(self.store.action(one)['dispatch_at'],moment.isoformat())

    def test_due_times_use_utc_and_naive_times_are_rejected(self):
        key=self.prepare(due='2020-01-01T10:00:00+05:30')
        self.assertEqual(self.store.action(key)['due_at'],'2020-01-01T04:30:00+00:00')
        with self.assertRaises(ValueError):self.prepare(day=2,due='2020-01-01T10:00:00')

    def test_reply_cancels_all_future_product_steps(self):
        self.store.save_contact('lead@example.org',{},[])
        key=self.prepare(); other=self.prepare(day=2)
        self.store.save_mail({'message_id':'reply','thread_id':'t','direction':'incoming','sender_email':'lead@example.org'})
        self.assertEqual(self.store.action(key)['status'],'cancelled')
        self.assertEqual(self.store.action(other)['status'],'cancelled')
        self.assertIsNone(self.store.reserve(key,10))

    def test_provider_events_do_not_downgrade_delivery_and_complaint_suppresses(self):
        key=self.prepare(); future=self.prepare(day=2)
        self.store.outcome(key,'sent',provider_id='provider')
        delivery={'eventType':'Delivery','mail':{'messageId':'provider'}}
        self.assertTrue(self.store.ingest_event(delivery));self.assertFalse(self.store.ingest_event(delivery))
        self.store.ingest_event({'eventType':'Send','mail':{'messageId':'provider'}})
        self.assertEqual(self.store.action(key)['status'],'delivered')
        self.store.ingest_event({'eventType':'Complaint','mail':{'messageId':'provider'}})
        self.store.outcome(key,'sent',gmail_id='archive')
        self.assertEqual(self.store.action(key)['status'],'complained')
        self.assertEqual(self.store.action(future)['status'],'cancelled')

    def test_five_email_enrollment_is_spaced_prepared_and_requires_permission(self):
        consent={'email':'lead@example.org','product':'manage','source':'Requested product introduction','recorded_at':now(),'series_permitted':True,'timezone':'UTC'}
        contact={'research_ready':True,'product':'manage','firm':'Example Firm'}
        keys=enroll(self.store,self.settings,consent,contact)
        self.assertEqual(len(keys),5)
        self.assertTrue(all(self.store.action(key)['status']=='prepared' for key in keys))
        start=datetime.fromisoformat(consent['recorded_at'])
        self.assertEqual([(datetime.fromisoformat(self.store.action(key)['due_at'])-start).days for key in keys],[0,2,5,9,13])
        with self.assertRaises(ValueError):enroll(self.store,self.settings,{**consent,'series_permitted':False},contact)
        with self.assertRaises(ValueError):enroll(self.store,self.settings,consent,{**contact,'product':'launch'})

    def test_disabled_send_never_contacts_aws(self):
        transport=MagicMock(send_enabled=False,campaigns_enabled=False); session=MagicMock()
        with self.assertRaises(PermissionError):send_reserved('missing',self.store,self.settings,transport,MagicMock(),session)
        session.client.assert_not_called()

    def test_rendering_escapes_personalization_and_rejects_destination_or_headers(self):
        campaign=load_campaigns()[0]
        rendered=render_email(campaign,campaign.steps[0],self.settings,contact_name='<script>bad</script>',firm_name='Firm & Co')
        self.assertNotIn('<script>bad',rendered['html'])
        self.assertIn('&lt;script&gt;',rendered['html'])
        bad=campaign.model_dump();bad['cta_url']='https://evil.example'
        with self.assertRaises(ValidationError):Campaign.model_validate(bad)
        bad=campaign.model_dump();bad['steps'][0]['subject']='Hello\r\nBcc: hidden@example.org'
        with self.assertRaises(ValidationError):Campaign.model_validate(bad)


class GmailTests(EmailBase):
    def gmail(self, handler):
        settings=self.settings.model_copy(update={'gmail_enabled':True,'oauth_production':True,
            'google_client_id':__import__('pydantic').SecretStr('test-client'),
            'google_client_secret':__import__('pydantic').SecretStr('test-secret'),
            'google_refresh_token':__import__('pydantic').SecretStr('test-refresh')})
        client=httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return Gmail(settings,client=client)

    def test_html_mail_is_normalized_to_text_without_active_content(self):
        raw='<p>Hello</p><script>send secret</script><style>hidden</style><p>Reply</p>'
        message={'id':'m','labelIds':['INBOX'],'payload':{'mimeType':'text/html','headers':[{'name':'From','value':'Client <client@example.org>'}],'body':{'data':base64.urlsafe_b64encode(raw.encode()).decode()}}}
        result=normalize_message(message,'mail@lexmom.com')
        self.assertIn('Hello',result['body']);self.assertNotIn('send secret',result['body'])
        self.assertNotIn('hidden',result['body']);self.assertEqual(result['sender_email'],'client@example.org')

    def test_token_refresh_retries_transient_failures_without_replaying_email_writes(self):
        calls=[]
        def handler(request):
            calls.append(request)
            if len(calls)<3:return httpx.Response(503)
            return httpx.Response(200,json={'access_token':'test','expires_in':3600,
                'scope':'https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.insert'})
        gmail=self.gmail(handler)
        with patch('shared.lexmom_gmail.time.sleep'):gmail.refresh()
        self.assertEqual(len(calls),3)
        self.assertTrue(all(request.url.host=='oauth2.googleapis.com' for request in calls))
        self.assertEqual(gmail.token,'test')

    def test_wrong_mailbox_and_missing_scopes_fail_closed(self):
        def handler(request):
            if request.url.host=='oauth2.googleapis.com':return httpx.Response(200,json={'access_token':'test','scope':'https://www.googleapis.com/auth/gmail.readonly'})
            raise AssertionError('Should not read a mailbox after scope failure')
        with self.assertRaises(MailboxError):self.gmail(handler).profile()
        gmail=self.gmail(lambda request:httpx.Response(200,json={'emailAddress':'other@example.org'}))
        gmail.token='test'
        with patch.object(gmail,'refresh'):
            with self.assertRaises(MailboxError):gmail.profile()

    def test_history_cursor_is_preserved_when_message_fetch_fails(self):
        self.store.set_metadata('gmail_history','10')
        gmail=MagicMock(spec=Gmail);gmail.settings=self.settings
        gmail.profile.return_value={'emailAddress':'mail@lexmom.com','historyId':'12'}
        gmail.request.side_effect=[{'historyId':'12','history':[{'messagesAdded':[{'message':{'id':'new'}}]}]},MailboxError('Read failed')]
        with self.assertRaises(MailboxError):Gmail.sync(gmail,self.store)
        self.assertEqual(self.store.metadata('gmail_history'),'10')

    def test_expired_history_recovers_and_commits_only_after_storage(self):
        self.store.set_metadata('gmail_history','10')
        gmail=MagicMock(spec=Gmail);gmail.settings=self.settings
        gmail.profile.return_value={'historyId':'30'}
        gmail.request.side_effect=[HistoryExpired('Expired'),{'messages':[{'id':'m'}]},
                                  {'id':'m','threadId':'t','labelIds':['SENT'],'payload':{'headers':[]}}]
        result=Gmail.sync(gmail,self.store)
        self.assertTrue(result['full_sync']);self.assertEqual(self.store.metadata('gmail_history'),'30')
        self.assertEqual(len(self.store.dashboard()['messages']),1)

    def test_lost_archive_acceptance_is_not_inserted_again(self):
        gmail=MagicMock(spec=Gmail);gmail.request.side_effect=[{},MailboxError('Response lost'),{}]
        with self.assertRaises(MailboxError):Gmail.archive_sent(gmail,b'mime','key',self.store)
        with self.assertRaises(MailboxError):Gmail.archive_sent(gmail,b'mime','key',self.store)
        self.assertEqual(sum(call.args[0]=='POST' for call in gmail.request.call_args_list),1)


class EmailApiTests(EmailBase):
    def test_current_previews_include_combined_and_retire_sixth_and_seventh(self):
        client=self.client()
        with patch.object(api.Settings,'from_env',return_value=self.settings):
            self.assertEqual(client.get(api.BASE+'/email/preview/both/5').status_code,200)
            for product in ('launch','manage','both'):
                for position in (6,7):self.assertEqual(client.get(api.BASE+f'/email/preview/{product}/{position}').status_code,404)
            data=client.get(api.BASE+'/email/data').json()
            self.assertTrue(data['readiness']['drafts_valid'])
            self.assertEqual(len(data['previews']),15)

    def client(self, role='operator'):
        app=FastAPI()
        async def authorize(request,write=False):
            if role is None:raise HTTPException(401,'Login required')
            return {'role':role}
        api.register_routes(app,authorize)
        return TestClient(app)

    def test_mailbox_routes_reject_anonymous_and_viewer(self):
        for role,status in ((None,401),('viewer',403)):
            client=self.client(role)
            self.assertEqual(client.get(api.BASE+'/email/data').status_code,status)
            self.assertEqual(client.get(api.BASE+'/email/preview/manage/1').status_code,status)
        self.assertEqual(self.client().post(api.BASE+'/email/send').status_code,409)

    def test_interest_confirmation_validates_input_and_does_not_send(self):
        client=self.client()
        self.store.save_contact('lead@example.org',{'product':'manage'},['Sending off'])
        self.store.save_mail({'message_id':'positive','direction':'incoming','sender_email':'lead@example.org',
                              'labels':['INBOX'],'subject':'A demo please'})
        with patch.object(api.Settings,'from_env',return_value=self.settings):
            self.assertEqual(client.post(api.BASE+'/email/confirm-interest',content=b'{').status_code,422)
            self.assertEqual(client.post(api.BASE+'/email/confirm-interest',json={'email':'lead@example.org','message_id':'positive','product':{}}).status_code,422)
            response=client.post(api.BASE+'/email/confirm-interest',json={'email':'lead@example.org','message_id':'positive','product':'manage'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['emails_sent'],0)
        self.assertTrue(self.store.engagement_activity()['lead@example.org']['confirmed_interest'])
        self.assertTrue(self.store.dashboard()['messages'][0]['interest_confirmed'])
        self.assertEqual(self.store.dashboard()['accepted_count'],0)

    def test_only_known_nonautomated_incoming_leads_can_be_reviewed(self):
        self.store.save_contact('lead@example.org',{'product':'manage'},['Sending off'])
        for index,extra in enumerate(({}, {'is_automated':True},{'labels':['SPAM']},{'sender_email':'unknown@example.org'},{'direction':'sent'})):
            self.store.save_mail({'message_id':str(index),'direction':'incoming','sender_email':'lead@example.org','labels':['INBOX'],**extra})
        messages={m['message_id']:m for m in self.store.dashboard()['messages']}
        self.assertTrue(messages['0']['interest_eligible'])
        self.assertTrue(all(not messages[str(i)]['interest_eligible'] for i in range(1,5)))

    def test_unsubscribe_scanner_get_has_no_side_effect_and_forged_post_fails(self):
        key=self.prepare();token=unsubscribe_token('lead@example.org','x'*40);client=self.client()
        with patch.object(api.Settings,'from_env',return_value=self.settings):
            self.assertEqual(client.get(api.BASE+'/email/unsubscribe/'+token).status_code,200)
            self.assertEqual(self.store.action(key)['status'],'queued')
            self.assertEqual(client.post(api.BASE+'/email/unsubscribe/'+token+'x').status_code,404)
            self.assertEqual(client.post(api.BASE+'/email/unsubscribe/'+token,data={'List-Unsubscribe':'One-Click'}).status_code,200)
            self.assertEqual(self.store.action(key)['status'],'cancelled')

    def test_only_public_artwork_is_exposed(self):
        client=self.client(None)
        self.assertEqual(client.get(api.BASE+'/email-assets/campaign-artwork-v3.json').status_code,404)
        self.assertEqual(client.get(api.BASE+'/email-assets/private.env').status_code,404)
        self.assertEqual(client.get(api.BASE+'/email-assets/lexmom-launch-day01-v3.png').status_code,200)


if __name__=='__main__':unittest.main()
