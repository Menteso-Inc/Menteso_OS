import unittest
from .agent import qualify
from .models import ExtractedFirm, ResearchRequest
from .rule_extraction import extract_rules
from .primary_facts import attorney_roster, postal_country
from .tools import _PublicHTML


class PrimaryFactsTests(unittest.TestCase):
    def page(self, extra='', path='/attorneys/'):
        text = 'Example Law LLP\nOur law firm. Litigation.\nAttorneys\nJane Doe\nEmily Home\nJohn Smith\nProfessional Staff\nSam Jones\nAddress\n550 California Street\nSuite 910\nSan Francisco, CA 94104\n' + extra
        return dict(url='https://example.com'+path, text=text, titles=['Example Law LLP'],
                    contact_headings=['Jane Doe','Emily Home','John Smith','Sam Jones'])

    def test_attorney_roster_excludes_staff_and_preserves_real_surname(self):
        page=self.page()
        self.assertEqual(attorney_roster(page)['count'],3)
        request=ResearchRequest(extraction_mode='rules')
        record=qualify(page['url'],ExtractedFirm.model_validate(extract_rules([page],request)),[page],request)
        self.assertEqual((record.size,record.size_basis,record.country,record.fit_status),(3,'published_roster','US','qualified'))

    def test_mixed_filtered_incomplete_and_truncated_directories_are_not_counts(self):
        for page in (self.page(path='/people/'), self.page('Load more'), self.page('Filter by'), self.page('Next page'), self.page('x'*60000)):
            self.assertIsNone(attorney_roster(page))

    def test_role_headings_cannot_be_counted_as_a_person(self):
        page=dict(url='https://example.com/team',text='Our Team\nAdvocate and Legal Consultant\nFounding Partner',contact_headings=['Our Team'])
        self.assertIsNone(attorney_roster(page))

    def test_explicit_attorney_menu_requires_each_named_profile(self):
        block='Attorneys\nJane Doe\nJohn Smith'
        page=dict(url='https://example.com/',text=block,contact_blocks=[block],links=['https://example.com/jane-doe/','https://example.com/john-smith/'])
        self.assertEqual(attorney_roster(page)['count'],2)
        page['links'].pop();self.assertIsNone(attorney_roster(page))

    def test_postal_address_requires_street_and_zip_not_just_state(self):
        for text in ('Office: New Jersey.', 'We serve Georgia.', 'New York, NY 10017'):
            self.assertFalse(postal_country(dict(text=text)))
        self.assertEqual(postal_country(dict(text='555 Richmond St. W., Suite 1200,\nToronto, On M5V 3B1'))[0][0],'CA')

    def test_forged_roster_size_and_partial_excerpt_cannot_ground_a_count(self):
        page=self.page(); request=ResearchRequest(extraction_mode='rules')
        proposal=extract_rules([page],request)
        proposal['size']=4
        for item in proposal['evidence']:
            if item['field']=='size': item['value']='4'
        record=qualify(page['url'],ExtractedFirm.model_validate(proposal),[page],request)
        self.assertIsNone(record.size)

    def test_navigation_duplicates_do_not_hide_buyer_profile_links(self):
        parser=_PublicHTML()
        parser.feed('<a href="/about">About</a>'*350 + '<a href="/attorneys/jane">Jane Doe</a>')
        self.assertIn('/attorneys/jane',parser.links)

    def test_location_suffix_and_labelled_email_preserve_person_boundaries(self):
        from .primary_facts import directory_entries
        page={'text':'Jane Doe\nManaging Partner | New York\nPh: (202) 555-0100 •\nE: jane@example.com'}
        self.assertEqual(directory_entries(page)[0]['email'],'jane@example.com')

    def test_multi_country_offices_qualify_without_inventing_headquarters(self):
        import json
        page=self.page()
        node={'@type':'LegalService','name':'Example Law LLP','url':'https://example.com/',
              'address':[{'addressCountry':'US'},{'addressCountry':'GB'}]}
        raw=json.dumps(node);page['text']+='\n'+raw;page['structured_data']=[raw]
        request=ResearchRequest(extraction_mode='rules')
        record=qualify(page['url'],ExtractedFirm.model_validate(extract_rules([page],request)),[page],request)
        self.assertEqual(record.countries,['GB','US']);self.assertIsNone(record.country)
        self.assertEqual(record.fit_status,'qualified')

    def test_contact_goal_requires_fresh_verification_not_just_firm_qualification(self):
        from .agent import contact_target_count
        from .test_product_pipeline import ProductPipelineTests
        from datetime import datetime,timezone
        factory=ProductPipelineTests();factory.setUp()
        try:
            record=factory.firm();record.provenance='live';record.researched_at=datetime.now(timezone.utc).isoformat()
            contact=record.contacts[0];contact.name=None;contact.email='info@example.com'
            contact.verification_status='valid';contact.verified_at=datetime.now(timezone.utc).date().isoformat()
            request=ResearchRequest(product='manage',target_contacts=50)
            self.assertEqual(contact_target_count([record.model_dump(),record.model_dump()],request),1)
            contact.verified_at='2000-01-01'
            self.assertEqual(contact_target_count([record.model_dump()],request),0)
        finally:factory.doCleanups()

    def test_met_inventory_goal_reuses_results_without_provider_calls(self):
        from unittest.mock import patch
        import tempfile
        from datetime import datetime,timezone
        from .agent import run_agent
        from .qualification import load_policy
        from .test_product_pipeline import ProductPipelineTests
        from shared.prospect_store import ProspectStore,targeting_key
        from shared.research_runtime import ResearchSession
        factory=ProductPipelineTests();factory.setUp()
        try:
            record=factory.firm();record.provenance='live';record.researched_at=datetime.now(timezone.utc).isoformat()
            contact=record.contacts[0];contact.name=None;contact.email='info@example.com'
            contact.verification_status='valid';contact.verified_at=datetime.now(timezone.utc).date().isoformat()
            request=ResearchRequest(product='manage',target_contacts=1,extraction_mode='rules')
            with tempfile.TemporaryDirectory() as directory:
                session=ResearchSession('prospect_research_agent',state_dir=directory,memory_dir=directory+'/memory')
                ProspectStore(session.agent_dir).save(targeting_key(request,load_policy().fingerprint),'seed',record)
                with patch('agents.prospect_research_agent.agent.live_preflight') as preflight,patch('agents.prospect_research_agent.tools.SourceTools') as source:
                    result=run_agent(request.model_dump(),session=session)
                preflight.assert_not_called();source.assert_not_called()
                self.assertEqual(result['status'],'success');self.assertTrue(result['tests']['passed'])
                self.assertTrue(result['reused_inventory'])
                self.assertEqual(result['data']['summary']['qualified_verified_inventory_contacts'],1)
                self.assertEqual(result['budget']['counts']['queries'],0)
        finally:factory.doCleanups()

    def test_count_does_not_accept_client_team_or_mixed_staff(self):
        for sentence in ('Our client has a team of 20 lawyers.', 'Our team of 25 lawyers and staff.', 'Previously led a team of 12 attorneys.'):
            page=dict(url='https://example.com/',text='Example Law firm. '+sentence,titles=['Example Law'])
            self.assertIsNone(extract_rules([page],ResearchRequest(extraction_mode='rules'))['size'])

    def test_canonical_brand_beats_description_and_conflicting_unlinked_alias(self):
        page=self.page()
        page['text'] += '\nPublished business structured data:\n'+__import__('json').dumps({'@type':'Organization','name':'Example Law LLP','url':'https://example.com/'})
        page['structured_data']=[__import__('json').dumps({'@type':'Organization','name':'Example Law LLP','url':'https://example.com/'})]
        proposal=extract_rules([page],ResearchRequest(extraction_mode='rules'))
        self.assertEqual(proposal['name'],'Example Law LLP')

    def test_long_biography_links_own_contact_section_but_not_footer_or_assistant(self):
        from .primary_facts import profile_contact
        page={'url':'https://example.com/people/jane','headings':['Jane Doe'],
              'text':'Jane Doe\nSenior Partner\n'+('A professional biography. '*80)+'\nContact\n+44 20 1234 5678\njane@example.com\nMemberships',
              'footer_blocks':[]}
        self.assertEqual(profile_contact(page)['email'],'jane@example.com')
        page['footer_blocks']=['jane@example.com'];self.assertIsNone(profile_contact(page))
        page['footer_blocks']=[];page['contact_headings']=['Jane Doe','John Smith']
        page['text']=page['text'].replace('Contact\n','Contact\nJohn Smith\n')
        self.assertIsNone(profile_contact(page))


if __name__=='__main__': unittest.main()
