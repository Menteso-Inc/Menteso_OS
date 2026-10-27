"""Offline social setup, destination isolation and publication failure cases."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
from dotenv import set_key, dotenv_values
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from agents.social_media_posting_agent import api, oauth, runtime
from agents.social_media_posting_agent.connectors import LinkedIn, YouTube, ProviderError, UncertainOutcome
from agents.social_media_posting_agent.models import Settings, PREFIX
from agents.social_media_posting_agent.store import Store
from agents.social_media_posting_agent.tools import load_drafts, media_digest
from agents.social_media_posting_agent import tools
from agents.social_media_posting_agent.agent import run_agent
from shared.research_runtime import ResearchSession


class SocialSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);env=self.root/'.env';env.touch()
        self.settings=Settings(state_dir=self.root/'state',env_file=env)
        self.app_settings=self.settings.model_copy(update={name:SecretStr('fixture-'+name) for name in (
            'google_client_id','google_client_secret','youtube_channel_id','linkedin_client_id','linkedin_client_secret','linkedin_organization_urn')})
        self.app_settings=self.app_settings.model_copy(update={'linkedin_product_approved':True})

    def client(self,role='operator'):
        app=FastAPI()
        async def auth(request,write=False):
            if request.headers.get('x-test-user')!='present':raise HTTPException(401)
            if write and request.headers.get('origin')!='https://os.menteso.com':raise HTTPException(403)
            return {'username':'fixture-operator','role':role}
        api.register_routes(app,auth)
        return TestClient(app,base_url='https://os.menteso.com')

    def headers(self):return {'x-test-user':'present','origin':'https://os.menteso.com'}

    def test_drafts_are_grounded_unique_and_private(self):
        rows=load_drafts();self.assertEqual(len(rows),5)
        self.assertEqual({r.platform for r in rows},{'linkedin','youtube'})
        self.assertEqual({r.product for r in rows},{'manage','launch'})
        self.assertTrue(all(r.status=='draft' and not r.scheduled_at for r in rows))
        self.assertEqual(len({r.key for r in rows}),len(rows))

    def test_configuration_distinguishes_app_and_connection(self):
        self.assertTrue(self.app_settings.app_configured('youtube'))
        self.assertFalse(self.app_settings.configured('youtube'))
        self.assertFalse(self.settings.publishing_enabled)
        with self.assertRaises(ValueError):self.settings.configured('unknown')

    def linkedin_fixture(self,refresh=True):
        import time
        settings=self.app_settings.model_copy(update={'linkedin_access_token':SecretStr('fixture-old-access'),
            'linkedin_refresh_token':SecretStr('fixture-old-refresh' if refresh else ''),
            'linkedin_organization_urn':SecretStr('urn:li:organization:123456'),
            'linkedin_expires_at':int(time.time())+86400,'linkedin_refresh_expires_at':int(time.time())+10*86400 if refresh else 0})
        for name in ('linkedin_client_id','linkedin_client_secret','linkedin_organization_urn','linkedin_access_token','linkedin_refresh_token',
                     'linkedin_expires_at','linkedin_refresh_expires_at','linkedin_product_approved','state_dir'):
            value=getattr(settings,name);value=value.get_secret_value() if hasattr(value,'get_secret_value') else str(value).lower() if isinstance(value,bool) else str(value)
            set_key(str(settings.env_file),PREFIX+name.upper(),value)
        set_key(str(settings.env_file),'UNRELATED_FIXTURE_SETTING','preserve')
        return settings

    def linkedin_identity_response(self,request,settings):
        if request.url.path.endswith('/introspectToken'):
            return httpx.Response(200,json={'active':True,'scope':['w_organization_social','rw_organization_admin','r_organization_social']})
        if request.url.path.endswith('/organizationAcls'):
            return httpx.Response(200,json={'elements':[{'organization':settings.linkedin_organization_urn.get_secret_value(),'state':'APPROVED','role':'ADMINISTRATOR'}]})
        raise AssertionError('Unexpected provider request')

    def test_pending_linkedin_review_blocks_oauth_before_state_or_provider_use(self):
        pending=self.app_settings.model_copy(update={'linkedin_product_approved':False})
        before=pending.env_file.read_text()
        with patch.object(Settings,'from_env',return_value=pending):
            response=self.client().post(api.BASE+'/oauth/linkedin/begin',json={},headers=self.headers())
        self.assertEqual(response.status_code,409);self.assertIn('review',response.json()['detail'])
        self.assertEqual(pending.env_file.read_text(),before)
        self.assertFalse(api.dashboard_data(pending)['connection_readiness']['linkedin']['available'])

    def test_approved_linkedin_requests_only_community_management_permissions(self):
        url,_=oauth.begin(self.app_settings,'linkedin','fixture-principal');query=parse_qs(urlsplit(url).query)
        self.assertEqual(set(query['scope'][0].split()),{'w_organization_social','rw_organization_admin','r_organization_social'})

    def test_linkedin_renews_once_then_persists_verified_access_without_extending_refresh_expiry(self):
        settings=self.linkedin_fixture();calls=[]
        def handler(request):
            if request.url.path.endswith('/accessToken'):
                calls.append(request);return httpx.Response(200,json={'access_token':'fixture-new-access','expires_in':60*86400,
                    'refresh_token':'fixture-new-refresh','refresh_token_expires_in':365*86400})
            return self.linkedin_identity_response(request,settings)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            adapter=LinkedIn(settings,client);result=adapter.verify();adapter.verify()
        saved=dotenv_values(settings.env_file)
        self.assertEqual(len(calls),1);self.assertEqual(result['renewal_mode'],'automatic')
        self.assertEqual(saved[PREFIX+'LINKEDIN_ACCESS_TOKEN'],'fixture-new-access')
        self.assertEqual(saved[PREFIX+'LINKEDIN_REFRESH_TOKEN'],'fixture-new-refresh')
        self.assertEqual(int(saved[PREFIX+'LINKEDIN_REFRESH_EXPIRES_AT']),settings.linkedin_refresh_expires_at)
        self.assertEqual(saved['UNRELATED_FIXTURE_SETTING'],'preserve')
        self.assertFalse(list(settings.env_file.parent.glob('.lexmom-social-*.env')))

    def test_linkedin_without_refresh_grant_keeps_valid_access_and_reports_reauthorization(self):
        settings=self.linkedin_fixture(refresh=False);calls=[]
        def handler(request):calls.append(request.url.path);return self.linkedin_identity_response(request,settings)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:result=LinkedIn(settings,client).verify()
        self.assertEqual(result['renewal_mode'],'owner_reauthorization');self.assertTrue(result['renewal_required_soon'])
        self.assertFalse(any(path.endswith('/accessToken') for path in calls))

    def test_linkedin_transient_renewal_failure_backs_off_across_worker_restarts(self):
        import os
        settings=self.linkedin_fixture();calls=[]
        def handler(request):
            if request.url.path.endswith('/accessToken'):calls.append(request);return httpx.Response(503)
            return self.linkedin_identity_response(request,settings)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result=LinkedIn(settings,client).verify()
            with patch.dict(os.environ,{PREFIX+'ENV_FILE':str(settings.env_file)}):reloaded=Settings.from_env()
            LinkedIn(reloaded,client).verify()
        self.assertTrue(result['connected']);self.assertEqual(len(calls),1)
        self.assertEqual(dotenv_values(settings.env_file)[PREFIX+'LINKEDIN_ACCESS_TOKEN'],'fixture-old-access')
        self.assertGreater(reloaded.linkedin_refresh_retry_at,0)

    def test_linkedin_denied_refresh_is_not_repeated_while_valid_access_is_preserved(self):
        import os
        settings=self.linkedin_fixture();calls=[]
        def handler(request):
            if request.url.path.endswith('/accessToken'):calls.append(request);return httpx.Response(400,json={'error':'invalid_grant'})
            return self.linkedin_identity_response(request,settings)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result=LinkedIn(settings,client).verify()
            with patch.dict(os.environ,{PREFIX+'ENV_FILE':str(settings.env_file)}):reloaded=Settings.from_env()
            LinkedIn(reloaded,client).verify()
        self.assertEqual(len(calls),1);self.assertTrue(reloaded.linkedin_refresh_blocked)
        self.assertEqual(result['renewal_mode'],'owner_reauthorization')

    def test_wrong_page_renewal_never_replaces_existing_credentials(self):
        settings=self.linkedin_fixture()
        def handler(request):
            if request.url.path.endswith('/accessToken'):return httpx.Response(200,json={'access_token':'fixture-wrong-page','expires_in':60*86400})
            if request.headers.get('authorization')=='Bearer fixture-wrong-page' and request.url.path.endswith('/organizationAcls'):
                return httpx.Response(200,json={'elements':[]})
            return self.linkedin_identity_response(request,settings)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:result=LinkedIn(settings,client).verify()
        self.assertTrue(result['connected'])
        saved=dotenv_values(settings.env_file);self.assertEqual(saved[PREFIX+'LINKEDIN_ACCESS_TOKEN'],'fixture-old-access')
        self.assertEqual(saved[PREFIX+'LINKEDIN_REFRESH_TOKEN'],'fixture-old-refresh')

    def test_concurrent_account_change_prevents_initial_token_persistence(self):
        settings=self.linkedin_fixture();set_key(str(settings.env_file),PREFIX+'LINKEDIN_ACCESS_TOKEN','fixture-other-operator')
        with httpx.Client(transport=httpx.MockTransport(lambda request:self.linkedin_identity_response(request,settings))) as client:
            with self.assertRaisesRegex(ProviderError,'configuration changed'):
                LinkedIn(settings,client).accept_token_response({'access_token':'fixture-candidate','expires_in':60*86400})
        self.assertEqual(dotenv_values(settings.env_file)[PREFIX+'LINKEDIN_ACCESS_TOKEN'],'fixture-other-operator')

    def test_initial_linkedin_consent_does_not_invent_a_refresh_grant(self):
        settings=self.linkedin_fixture()
        with httpx.Client(transport=httpx.MockTransport(lambda request:self.linkedin_identity_response(request,settings))) as client:
            result=LinkedIn(settings,client).accept_token_response({'access_token':'fixture-new-consent','expires_in':60*86400})
        self.assertEqual(result['renewal_mode'],'owner_reauthorization')
        self.assertEqual(dotenv_values(settings.env_file)[PREFIX+'LINKEDIN_REFRESH_TOKEN'],'')

    def test_provider_rate_limit_is_not_retried_and_cooldown_survives_restart(self):
        calls=[]
        def handler(request):calls.append(request);return httpx.Response(429,headers={'Retry-After':'7200'})
        from agents.social_media_posting_agent.connectors import Official
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            for _ in range(2):
                with self.assertRaises(ProviderError):Official(self.settings,client).request('GET','https://api.linkedin.com/rest/organizationAcls')
        self.assertEqual(len(calls),1)
        import time
        self.assertGreater(Store(self.settings.state_dir).metadata('api_backoff_linkedin')['retry_at'],time.time()+7100)

    def test_provider_cooldown_does_not_block_other_platform(self):
        from agents.social_media_posting_agent.connectors import Official
        Store(self.settings.state_dir).metadata('api_backoff_linkedin',{'retry_at':9999999999})
        with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'ok':True}))) as client:
            response=Official(self.settings,client).request('GET','https://www.googleapis.com/youtube/v3/channels')
        self.assertTrue(response.json()['ok'])

    def test_post_creation_time_is_saved_once_and_exposed_in_dashboard(self):
        store=Store(self.settings.state_dir);draft=load_drafts()[0];store.install([draft])
        first=store.get(draft.key).created_at
        self.assertIsNotNone(first);self.assertIsNotNone(first.utcoffset())
        store.install([draft]);self.assertEqual(store.get(draft.key).created_at,first)
        saved=store.update(draft.key,1,lambda row:row.model_copy(update={'title':'An updated title','revision':2}))
        self.assertEqual(saved.created_at,first)
        row=api.dashboard_data(self.settings)['drafts'][0]
        self.assertIsNotNone(row['created_at']);self.assertIsNone(row['published_at'])

    def test_legacy_dates_remain_unknown_and_only_confirmed_posts_get_posted_time(self):
        store=Store(self.settings.state_dir);draft=load_drafts()[0]
        legacy=draft.model_dump(mode='json');legacy.pop('created_at');legacy.pop('published_at')
        with store.connection() as db:db.execute('INSERT INTO posts VALUES (?,?)',(draft.key,json.dumps(legacy)))
        self.assertIsNone(store.get(draft.key).created_at)
        store.finish(draft.key,'processing');self.assertIsNone(store.get(draft.key).published_at)
        store.finish(draft.key,'needs_reconciliation');self.assertIsNone(store.get(draft.key).published_at)
        store.finish(draft.key,'published');first=store.get(draft.key).published_at
        self.assertIsNotNone(first);self.assertIsNotNone(first.utcoffset())
        store.finish(draft.key,'published');self.assertEqual(store.get(draft.key).published_at,first)
        self.assertIsNone(store.get(draft.key).created_at)

    def test_setup_never_enters_a_provider_publish(self):
        with patch.object(LinkedIn,'publish') as linked,patch.object(YouTube,'publish') as youtube:
            self.assertEqual(runtime.publish_due(self.settings)['posts_published'],0)
        linked.assert_not_called();youtube.assert_not_called()

    def test_adapters_block_before_any_network_or_upload(self):
        calls=[]
        transport=httpx.MockTransport(lambda request:calls.append(request))
        with httpx.Client(transport=transport) as client:
            for adapter in (LinkedIn(self.settings,client),YouTube(self.settings,client)):
                with self.assertRaises(PermissionError):adapter.publish(load_drafts()[0])
        self.assertEqual(calls,[])

    def test_monitor_without_credentials_uses_no_providers(self):
        with patch.object(LinkedIn,'verify') as linked,patch.object(YouTube,'verify') as youtube:
            data=runtime.monitor(self.settings)
        self.assertTrue(all(not row['connected'] for row in data['platforms'].values()))
        linked.assert_not_called();youtube.assert_not_called()

    def test_metrics_failure_preserves_verified_connection(self):
        settings=self.app_settings.model_copy(update={'linkedin_access_token':SecretStr('fixture-token')})
        with patch.object(LinkedIn,'verify',return_value={'connected':True,'destination':'LexMom'}),patch.object(LinkedIn,'metrics',side_effect=ProviderError('Read permission unavailable')):
            data=runtime.monitor(settings)
        self.assertTrue(data['platforms']['linkedin']['connected'])
        self.assertIn('metrics_reason',data['platforms']['linkedin'])

    def test_wrong_youtube_channel_is_rejected(self):
        with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'items':[{'id':'another-brand'}]}))) as client:
            adapter=YouTube(self.app_settings,client);adapter.token='fixture-token'
            with self.assertRaisesRegex(ProviderError,'not the configured'):adapter.verify()

    def test_edit_invalidates_approval(self):
        store=Store(self.settings.state_dir);draft=load_drafts()[0];draft.status='approved';draft.approval_digest=draft.digest();store.install([draft])
        with patch.object(Settings,'from_env',return_value=self.settings):
            r=self.client().post(api.BASE+'/'+draft.key+'/edit',json={'revision':1,'title':draft.title,'caption':draft.caption+' Updated.'},headers=self.headers())
        self.assertEqual(r.status_code,200);saved=store.get(draft.key)
        self.assertEqual(saved.status,'draft');self.assertIsNone(saved.approval_digest)
        self.assertEqual(saved.revision,2)

    def test_schedule_and_publish_blocked(self):
        with patch.object(Settings,'from_env',return_value=self.settings):
            client=self.client()
            for action in ('schedule','publish'):
                self.assertEqual(client.post(api.BASE+'/missing/'+action,json={},headers=self.headers()).status_code,409)

    def test_dashboard_dispatch_is_blocked_before_worker_in_setup(self):
        with patch.object(Settings,'from_env',return_value=self.settings),patch.object(api,'publish_due') as worker:
            response=self.client().post(api.BASE+'/dispatch',json={},headers=self.headers())
        self.assertEqual(response.status_code,409);worker.assert_not_called()

    def test_dashboard_dispatch_requires_operator_origin_and_no_overrides(self):
        enabled=self.settings.model_copy(update={'publishing_enabled':True})
        with patch.object(Settings,'from_env',return_value=enabled),patch.object(api,'publish_due') as worker:
            self.assertEqual(self.client('viewer').post(api.BASE+'/dispatch',json={},headers=self.headers()).status_code,403)
            self.assertEqual(self.client().post(api.BASE+'/dispatch',json={},headers={'x-test-user':'present'}).status_code,403)
            self.assertEqual(self.client().post(api.BASE+'/dispatch',json={'publishing_enabled':True},headers=self.headers()).status_code,422)
        worker.assert_not_called()

    def test_dashboard_dispatch_can_run_reviewed_queue_after_future_activation(self):
        enabled=self.settings.model_copy(update={'publishing_enabled':True})
        with patch.object(Settings,'from_env',return_value=enabled),patch.object(api,'publish_due',return_value={'posts_published':0,'publishing_enabled':True}) as worker:
            response=self.client().post(api.BASE+'/dispatch',json={},headers=self.headers())
        self.assertEqual(response.status_code,200);worker.assert_called_once_with(enabled)

    def test_viewer_and_cross_origin_cannot_change_content(self):
        self.assertEqual(self.client('viewer').get(api.BASE+'/data',headers=self.headers()).status_code,403)
        self.assertEqual(self.client().post(api.BASE+'/prepare',json={},headers={'x-test-user':'present','origin':'https://elsewhere.example'}).status_code,403)
        self.assertEqual(self.client().get(api.BASE+'/data').status_code,401)

    def test_private_snapshot_contains_no_credentials(self):
        data=api.dashboard_data(self.app_settings)
        self.assertNotIn('fixture-',json.dumps(data))
        self.assertFalse(data['publishing_enabled'])

    def test_approval_requires_configured_destination(self):
        store=Store(self.settings.state_dir);draft=load_drafts()[0];store.install([draft])
        with patch.object(Settings,'from_env',return_value=self.settings):
            response=self.client().post(api.BASE+'/'+draft.key+'/approve',json={'revision':1},headers=self.headers())
        self.assertEqual(response.status_code,409)

    def test_stale_edit_and_render_do_not_touch_media(self):
        store=Store(self.settings.state_dir);draft=next(d for d in load_drafts() if d.platform=='youtube');store.install([draft])
        with patch.object(Settings,'from_env',return_value=self.settings),patch.object(api,'render_video') as render:
            response=self.client().post(api.BASE+'/'+draft.key+'/render',json={'revision':2},headers=self.headers())
        self.assertEqual(response.status_code,409);render.assert_not_called()

    def test_renderer_failure_preserves_draft_and_redacts_untrusted_error(self):
        store=Store(self.settings.state_dir);draft=next(d for d in load_drafts() if d.platform=='youtube');store.install([draft])
        before=store.get(draft.key)
        with patch.object(Settings,'from_env',return_value=self.settings),patch.object(api,'render_video',side_effect=ValueError('fixture-private-value')):
            with self.assertLogs(api.__name__,level='WARNING') as messages:
                response=self.client().post(api.BASE+'/'+draft.key+'/render',json={'revision':1},headers=self.headers())
        self.assertEqual(response.status_code,503)
        self.assertNotIn('fixture-private-value',response.text+' '.join(messages.output))
        self.assertEqual(store.get(draft.key),before)

    def test_successful_render_saves_a_new_unapproved_revision(self):
        store=Store(self.settings.state_dir);draft=next(d for d in load_drafts() if d.platform=='youtube');store.install([draft])
        with patch.object(Settings,'from_env',return_value=self.settings),patch.object(api,'render_video',return_value='fixture-video.mp4'):
            response=self.client().post(api.BASE+'/'+draft.key+'/render',json={'revision':1},headers=self.headers())
        self.assertEqual(response.status_code,200)
        saved=store.get(draft.key)
        self.assertEqual((saved.revision,saved.video,saved.status),(2,'fixture-video.mp4','draft'))
        self.assertIsNone(saved.scheduled_at);self.assertIsNone(saved.approval_digest)

    def test_render_reuses_identical_artwork_and_bounds_decoder_workers(self):
        from types import SimpleNamespace
        draft=next(d for d in load_drafts() if d.platform=='youtube')
        def run(command,**kwargs):
            self.assertIn(['-threads','1'],[command[i:i+2] for i in range(command.index('-i'))])
            Path(command[-1]).write_bytes(b'fixture-rendered-video')
            return SimpleNamespace(returncode=0,stderr=b'')
        with patch('imageio_ffmpeg.get_ffmpeg_exe',return_value='fixture-ffmpeg'),patch.object(tools.subprocess,'run',side_effect=run) as runner:
            first=tools.render_video(draft,self.settings)
            draft.video=first;draft.revision+=1
            self.assertEqual(tools.render_video(draft,self.settings),first)
        self.assertEqual(runner.call_count,1)

    def test_pause_cancels_a_planned_time(self):
        store=Store(self.settings.state_dir);draft=load_drafts()[0];draft.status='scheduled';draft.scheduled_at=datetime.now(timezone.utc)+timedelta(days=1);store.install([draft])
        with patch.object(Settings,'from_env',return_value=self.settings):
            response=self.client().post(api.BASE+'/'+draft.key+'/pause',json={'revision':1},headers=self.headers())
        self.assertEqual(response.status_code,200);self.assertIsNone(store.get(draft.key).scheduled_at)

    def test_interrupted_write_never_returns_to_scheduled(self):
        store=Store(self.settings.state_dir);draft=load_drafts()[0];draft.status='publishing';store.install([draft]);store.recover_interrupted()
        self.assertEqual(store.get(draft.key).status,'needs_reconciliation')
        with self.assertRaises(ValueError):store.update(draft.key,1,lambda value:value)

    def begin(self):
        url,binding=oauth.begin(self.app_settings,'youtube','fixture-principal')
        return parse_qs(urlsplit(url).query)['state'][0],binding

    def test_oauth_requests_dedicated_scopes_and_offline_access(self):
        url,_=oauth.begin(self.app_settings,'youtube','fixture-principal');query=parse_qs(urlsplit(url).query)
        self.assertEqual(query['access_type'],['offline']);self.assertIn('code_challenge',query)
        self.assertNotIn('gmail',' '.join(query['scope']))
        self.assertNotIn('fixture-google_client_secret',url)

    def test_oauth_is_bound_to_browser_operator_and_exact_destination(self):
        state,binding=self.begin()
        for args in [(state,'wrong','fixture-principal'),(state,binding,'other'),('wrong',binding,'fixture-principal')]:
            with self.assertRaises(ValueError):oauth.consume(self.app_settings,'youtube',*args)
        changed=self.app_settings.model_copy(update={'youtube_channel_id':SecretStr('another-channel')})
        with self.assertRaises(ValueError):oauth.consume(changed,'youtube',state,binding,'fixture-principal')
        self.assertIn('verifier',oauth.consume(self.app_settings,'youtube',state,binding,'fixture-principal'))

    def test_oauth_cannot_be_replayed(self):
        state,binding=self.begin();oauth.consume(self.app_settings,'youtube',state,binding,'fixture-principal')
        with self.assertRaises(ValueError):oauth.consume(self.app_settings,'youtube',state,binding,'fixture-principal')

    def test_expired_oauth_cannot_exchange(self):
        state,binding=self.begin()
        with patch.object(oauth.time,'time',return_value=0):
            with self.assertRaises(ValueError):oauth.consume(self.app_settings,'youtube',state,binding,'fixture-principal')

    def test_unconfigured_oauth_never_enters_provider_flow(self):
        with patch.object(Settings,'from_env',return_value=self.settings):
            response=self.client().post(api.BASE+'/oauth/youtube/begin',json={},headers=self.headers())
        self.assertEqual(response.status_code,409)

    def test_oauth_callback_requires_browser_binding_and_has_no_provider_replay(self):
        with patch.object(Settings,'from_env',return_value=self.app_settings),patch.object(oauth,'complete',return_value={'connected':True}) as complete,patch.object(api,'monitor'):
            client=self.client();started=client.post(api.BASE+'/oauth/youtube/begin',json={},headers=self.headers())
            self.assertEqual(started.status_code,200)
            self.assertIn('HttpOnly',started.headers['set-cookie']);self.assertIn('Secure',started.headers['set-cookie'])
            state=parse_qs(urlsplit(started.json()['authorization_url']).query)['state'][0]
            callback=api.BASE+'/oauth/callback/youtube?state='+state+'&code=fixture-code'
            result=client.get(callback,headers=self.headers(),follow_redirects=False)
            self.assertEqual(result.status_code,303)
            self.assertEqual(result.headers['referrer-policy'],'no-referrer')
            self.assertNotIn('fixture-code',result.headers['location'])
            self.assertEqual(complete.call_count,1)
            client.get(callback,headers=self.headers(),follow_redirects=False)
            self.assertEqual(complete.call_count,1)

    def test_draft_preparation_self_tests_and_memory_are_real(self):
        session=ResearchSession('social_media_posting_agent',state_dir=self.root/'runs',memory_dir=self.root/'memory')
        result=run_agent(settings=self.settings,session=session)
        self.assertEqual(result['status'],'success');self.assertTrue(result['tests']['passed'])
        self.assertEqual(result['posts_published'],0);self.assertEqual(len(Store(self.settings.state_dir).list()),5)
        memory=json.loads(session.memory_path.read_text())
        self.assertEqual(memory['stats']['total_runs'],1)

    def test_duplicate_claim_is_a_clear_blocker(self):
        store=Store(self.settings.state_dir);draft=load_drafts()[0]
        draft.scheduled_at=datetime.now(timezone.utc)-timedelta(seconds=1);draft.status='scheduled';draft.approval_digest=draft.digest();store.install([draft])
        store.claim(draft.key,2)
        with self.assertRaises(ValueError):store.claim(draft.key,2)
        self.assertEqual(len(store.list()),1)

    def test_edited_product_cannot_link_to_other_brand_or_product(self):
        draft=load_drafts()[0]
        for link in ('https://example.com/manage/','https://lexmom.com/launch/','https://lexmom.com/manage-fake/'):
            with self.assertRaises(ValueError):
                type(draft).model_validate({**draft.model_dump(),'caption':'Explore this product: '+link})

    def publication_fixture(self):
        settings=self.app_settings.model_copy(update={'publishing_enabled':True,'linkedin_access_token':SecretStr('fixture-token')})
        draft=load_drafts()[0];draft.status='scheduled';draft.scheduled_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        draft.asset_digest=media_digest(draft,settings);draft.destination_digest=settings.destination_digest('linkedin');draft.approval_digest=draft.digest()
        Store(settings.state_dir).install([draft])
        return settings,draft

    def test_destination_changes_block_before_claim_or_provider(self):
        settings,draft=self.publication_fixture()
        changed=settings.model_copy(update={'linkedin_organization_urn':SecretStr('another-brand')})
        with patch.object(LinkedIn,'verify') as verify,patch.object(LinkedIn,'publish') as publish:
            result=runtime.publish_due(changed)
        verify.assert_not_called();publish.assert_not_called();self.assertEqual(result['posts_published'],0)
        self.assertEqual(Store(settings.state_dir).get(draft.key).status,'scheduled')

    def test_wrong_channel_consent_never_replaces_saved_credentials(self):
        from agents.social_media_posting_agent.models import YOUTUBE_SCOPES
        response=httpx.Response(200,json={'refresh_token':'fixture-candidate','scope':' '.join(YOUTUBE_SCOPES)})
        with patch.object(oauth.Official,'request',return_value=response),patch.object(YouTube,'verify',side_effect=ProviderError('Wrong channel')),patch.object(oauth,'persist_private') as persist:
            with self.assertRaises(ProviderError):oauth.complete(self.app_settings,'youtube','fixture-code',{'verifier':'fixture-verifier'})
        persist.assert_not_called()

    def test_ambiguous_provider_acceptance_never_blindly_retries(self):
        settings,draft=self.publication_fixture()
        with patch.object(LinkedIn,'verify',return_value={'connected':True}),patch.object(LinkedIn,'publish',side_effect=UncertainOutcome('No receipt')) as publish:
            runtime.publish_due(settings);runtime.publish_due(settings)
        self.assertEqual(publish.call_count,1)
        self.assertEqual(Store(settings.state_dir).get(draft.key).status,'needs_reconciliation')

    def youtube_fixture(self):
        settings=self.app_settings.model_copy(update={'google_refresh_token':SecretStr('fixture-youtube-refresh')})
        for name in ('google_client_id','google_client_secret','google_refresh_token','youtube_channel_id'):
            set_key(str(settings.env_file),PREFIX+name.upper(),getattr(settings,name).get_secret_value())
        set_key(str(settings.env_file),'UNRELATED_FIXTURE_SETTING','preserve')
        return settings

    def test_youtube_visibility_defaults_private_and_is_part_of_approval(self):
        draft=next(row for row in load_drafts() if row.platform=='youtube')
        self.assertEqual(draft.privacy_status,'private');original=draft.digest()
        draft.privacy_status='public';self.assertNotEqual(original,draft.digest())
        with self.assertRaises(ValueError):type(draft).model_validate({**draft.model_dump(),'privacy_status':'invalid'})

    def test_youtube_visibility_edit_invalidates_approval_and_rejects_invalid_values(self):
        draft=next(row for row in load_drafts() if row.platform=='youtube');draft.status='approved';draft.approval_digest=draft.digest()
        store=Store(self.settings.state_dir);store.install([draft])
        payload={'revision':1,'title':draft.title,'caption':draft.caption,'privacy_status':'unlisted'}
        with patch.object(Settings,'from_env',return_value=self.settings):
            client=self.client();self.assertEqual(client.post(api.BASE+'/'+draft.key+'/edit',json={**payload,'privacy_status':'invalid'},headers=self.headers()).status_code,422)
            response=client.post(api.BASE+'/'+draft.key+'/edit',json=payload,headers=self.headers())
        self.assertEqual(response.status_code,200);saved=store.get(draft.key)
        self.assertEqual((saved.status,saved.privacy_status,saved.revision),('draft','unlisted',2));self.assertIsNone(saved.approval_digest)

    def test_youtube_upload_uses_exact_selected_visibility_in_offline_transport(self):
        from agents.social_media_posting_agent.models import YOUTUBE_SCOPES
        settings=self.youtube_fixture().model_copy(update={'publishing_enabled':True});requested=[]
        def handler(request):
            if request.url.path=='/token':return httpx.Response(200,json={'access_token':'fixture-access','scope':' '.join(YOUTUBE_SCOPES)})
            if request.url.path=='/youtube/v3/channels':return httpx.Response(200,json={'items':[{'id':settings.youtube_channel_id.get_secret_value()}]})
            if request.method=='POST' and request.url.path=='/upload/youtube/v3/videos':
                requested.append(json.loads(request.content)['status']['privacyStatus'])
                return httpx.Response(200,headers={'Location':'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=fixture-upload'})
            if request.method=='PUT':return httpx.Response(200,json={'id':'abcdefghijk'})
            raise AssertionError('Unexpected request')
        for visibility in ('private','unlisted','public'):
            draft=next(row for row in load_drafts() if row.platform=='youtube');draft.video='fixture-video.mp4';draft.privacy_status=visibility
            tools.media_path(settings,draft.video).write_bytes(b'fixture-video')
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:YouTube(settings,client).publish(draft)
        self.assertEqual(requested,['private','unlisted','public'])

    def test_youtube_processing_checks_visibility_and_does_not_mark_private_upload_public(self):
        settings=self.youtube_fixture();key=PREFIX+'RECEIPT_FIXTURE';set_key(str(settings.env_file),key,'abcdefghijk')
        for expected,actual,outcome in [('private','private','uploaded'),('unlisted','unlisted','uploaded'),('public','public','published'),('private','public','needs_reconciliation')]:
            payload={'items':[{'snippet':{'channelId':settings.youtube_channel_id.get_secret_value()},'status':{'uploadStatus':'processed','privacyStatus':actual},'processingDetails':{'processingStatus':'succeeded'}}]}
            with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=payload))) as client:
                adapter=YouTube(settings,client);adapter.token='fixture-access'
                with patch.object(adapter,'verify'):self.assertEqual(adapter.processing_status(key,expected),outcome)
        store=Store(settings.state_dir);draft=next(row for row in load_drafts() if row.platform=='youtube');store.install([draft]);store.finish(draft.key,'uploaded')
        self.assertIsNone(store.get(draft.key).published_at)
        with self.assertRaises(ValueError):store.update(draft.key,1,lambda value:value)

    def test_disconnect_requires_operator_same_origin_and_explicit_confirmation(self):
        with patch.object(Settings,'from_env',return_value=self.settings),patch.object(api,'disconnect_youtube') as disconnect:
            client=self.client();path=api.BASE+'/youtube/disconnect';confirmation={'confirm':'disconnect-youtube-and-remove-data'}
            self.assertEqual(client.post(path,json={}).status_code,401)
            self.assertEqual(self.client('viewer').post(path,json=confirmation,headers=self.headers()).status_code,403)
            self.assertEqual(client.post(path,json=confirmation,headers={'x-test-user':'present'}).status_code,403)
            self.assertEqual(client.post(path,json={},headers=self.headers()).status_code,422)
        disconnect.assert_not_called()

    def test_disconnect_revokes_and_removes_only_youtube_api_data(self):
        from agents.social_media_posting_agent.privacy import disconnect_youtube
        settings=self.youtube_fixture();rows=load_drafts();store=Store(settings.state_dir);store.install(rows)
        youtube=next(row for row in rows if row.platform=='youtube');reference=PREFIX+'RECEIPT_'+youtube.key.replace('-','_').upper()
        set_key(str(settings.env_file),reference,'fixture-provider-receipt');store.metadata('connections',{'platforms':{'youtube':{'connected':True,'metrics':{'views':99}},'linkedin':{'connected':True}}})
        calls=[]
        def handler(request):calls.append(request);return httpx.Response(200)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:result=disconnect_youtube(settings,client)
        self.assertEqual(len(calls),1);self.assertEqual(calls[0].url.host,'oauth2.googleapis.com');self.assertEqual(calls[0].url.path,'/revoke')
        saved=dotenv_values(settings.env_file);self.assertEqual(saved[PREFIX+'GOOGLE_REFRESH_TOKEN'],'');self.assertEqual(saved[reference],'')
        self.assertEqual(saved['UNRELATED_FIXTURE_SETTING'],'preserve');self.assertEqual(saved[PREFIX+'GOOGLE_CLIENT_SECRET'],'fixture-google_client_secret')
        self.assertNotIn('youtube',store.metadata('connections')['platforms']);self.assertTrue(store.metadata('connections')['platforms']['linkedin']['connected'])
        self.assertEqual(len(store.list()),5);self.assertEqual(result['youtube_videos_deleted'],0)

    def test_failed_revocation_preserves_connection_and_data(self):
        from agents.social_media_posting_agent.privacy import disconnect_youtube
        settings=self.youtube_fixture();before=settings.env_file.read_bytes();store=Store(settings.state_dir);store.metadata('connections',{'platforms':{'youtube':{'metrics':{'views':99}}}})
        with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(503))) as client:
            with self.assertRaises(ProviderError):disconnect_youtube(settings,client)
        self.assertEqual(settings.env_file.read_bytes(),before);self.assertEqual(store.metadata('connections')['platforms']['youtube']['metrics']['views'],99)

    def test_stale_disconnect_never_revokes_a_replacement_account(self):
        from agents.social_media_posting_agent.privacy import disconnect_youtube
        settings=self.youtube_fixture();set_key(str(settings.env_file),PREFIX+'GOOGLE_REFRESH_TOKEN','fixture-new-grant');calls=[]
        with httpx.Client(transport=httpx.MockTransport(lambda request:calls.append(request))) as client:
            with self.assertRaises(ProviderError):disconnect_youtube(settings,client)
        self.assertEqual(calls,[]);self.assertEqual(dotenv_values(settings.env_file)[PREFIX+'GOOGLE_REFRESH_TOKEN'],'fixture-new-grant')

    def test_confirmed_google_revocation_purges_cache_without_new_consent_or_upload(self):
        from agents.social_media_posting_agent.connectors import AuthorizationRevoked
        settings=self.youtube_fixture();store=Store(settings.state_dir);store.metadata('connections',{'platforms':{'youtube':{'metrics':{'views':99}}}})
        with patch.object(YouTube,'verify',side_effect=AuthorizationRevoked('Authorization revoked',400)),patch.object(YouTube,'processing_status') as processing:
            result=runtime.monitor(settings)
        self.assertFalse(result['platforms']['youtube']['connected']);self.assertNotIn('metrics',result['platforms']['youtube'])
        self.assertEqual(dotenv_values(settings.env_file)[PREFIX+'GOOGLE_REFRESH_TOKEN'],'');processing.assert_not_called()

    def test_google_invalid_client_is_not_misclassified_as_revocation(self):
        from agents.social_media_posting_agent.connectors import AuthorizationRevoked
        settings=self.youtube_fixture();before=settings.env_file.read_bytes()
        with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(400,json={'error':'invalid_client'}))) as client:
            try:YouTube(settings,client).headers()
            except AuthorizationRevoked:self.fail('Invalid client must preserve the grant')
            except ProviderError:pass
            else:self.fail('Invalid client must fail')
        self.assertEqual(settings.env_file.read_bytes(),before)

    def test_google_invalid_grant_is_recognized_without_exposing_response(self):
        from agents.social_media_posting_agent.connectors import AuthorizationRevoked
        settings=self.youtube_fixture()
        with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(400,json={'error':'invalid_grant','error_description':'fixture-private-detail'}))) as client:
            with self.assertRaises(AuthorizationRevoked) as raised:YouTube(settings,client).headers()
        self.assertNotIn('fixture-private-detail',str(raised.exception))

    def test_public_verification_pages_expose_only_app_disclosures(self):
        client=self.client()
        for page in ('about','privacy'):
            response=client.get(api.BASE+'/'+page)
            self.assertEqual(response.status_code,200);self.assertIn('LexMom',response.text)
            self.assertNotIn('fixture-',response.text);self.assertIn("default-src 'none'",response.headers['content-security-policy'])
        self.assertEqual(client.get(api.BASE+'/data').status_code,401)


if __name__=='__main__':unittest.main()
