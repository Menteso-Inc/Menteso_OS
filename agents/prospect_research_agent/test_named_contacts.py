"""Source boundaries, source grounding and free-credit guards, without network."""
import json
import os
import unittest
from unittest.mock import patch

from .agent import qualify
from .models import ExtractedFirm, ResearchRequest
from .rule_extraction import extract_rules
from .tools import SourceError, SourceTools, _PublicHTML
from shared.research_runtime import RunBudget


class NamedContactTests(unittest.TestCase):
    def page(self, html):
        parser = _PublicHTML()
        parser.feed('<title>Example Law</title><p>Our law firm is in United States. Our firm has 3 attorneys. Litigation.</p>' + html)
        return {"url": "https://example.com/team", "text": parser.text(), "titles": parser.titles,
                "headings": parser.headings, "contact_headings": parser.contact_headings,
                "structured_data": parser.structured_parts, "contact_blocks": parser.contact_blocks, "footer_blocks": parser.footer_blocks}

    def record(self, html):
        page = self.page(html)
        request = ResearchRequest(extraction_mode="rules", product="both")
        return qualify(page["url"], ExtractedFirm.model_validate(extract_rules([page], request)), [page], request)

    def test_published_person_schema_produces_grounded_name_role_and_email(self):
        node = {"@type": "Person", "name": "Jane Doe", "jobTitle": "Managing Partner", "email": "jane@example.com", "url": "https://example.com/team/jane"}
        row = self.record('<script type="application/ld+json">' + json.dumps(node) + '</script>')
        self.assertEqual(row.fit_status, "qualified")
        self.assertEqual(row.contacts[0].name, "Jane Doe")
        self.assertEqual(row.contacts[0].association_status, "sourced")
        self.assertTrue(row.contacts[0].buyer_role_match)
        self.assertFalse(row.contacts[0].research_ready)
        self.assertFalse(row.outreach_eligible)
        self.assertEqual(row.name, "Example Law")

    def test_explicit_team_cards_keep_two_people_separate(self):
        html = ''.join(f'<div class="team-member"><h2>{name}</h2><p>{role}</p><a href="mailto:{email}">Email</a></div>'
                       for name, role, email in [('Jane Doe', 'Managing Partner', 'jane@example.com'), ('John Smith', 'Associate', 'john@example.com')])
        row = self.record(html)
        self.assertEqual([(c.name, c.email) for c in row.contacts], [('Jane Doe', 'jane@example.com'), ('John Smith', 'john@example.com')])
        self.assertTrue(all(c.association_status == "sourced" for c in row.contacts))
        self.assertFalse(row.contacts[1].buyer_role_match)

    def test_root_inbox_can_be_enriched_by_a_later_published_profile(self):
        page = self.page('<p>jane@example.com</p>')
        detail = self.page('<div class="profile-card"><h2>Jane Doe</h2><p>Partner</p><p>jane@example.com</p></div>')
        output = extract_rules([page, detail], ResearchRequest(extraction_mode="rules"))
        self.assertEqual(output['contacts'][0]['name'], 'Jane Doe')

    def test_sourced_person_can_gain_a_role_from_a_later_profile(self):
        first=self.page('<div class="team-member"><h2>Jane Doe</h2><p>jane@example.com</p></div>')
        later=self.page('<h1>Jane Doe</h1><p>Partner</p><p>jane@example.com</p>')
        data=extract_rules([first,later],ResearchRequest(extraction_mode='rules'))
        self.assertEqual(data['contacts'][0]['role'],'Partner')

    def test_current_profile_and_roster_outrank_old_homepage_testimonial_title(self):
        home=self.page('<h1>Jane Doe</h1><p>Senior Associate</p>');home['url']='https://example.com/'
        roster=self.page('<h1>Our Team</h1><h2>Jane Doe</h2><p>Partner</p><p>jane@example.com</p>')
        detail=self.page('<h1>Jane Doe</h1><p>Partner</p><p>jane@example.com</p>');detail['url']='https://example.com/team/jane'
        data=extract_rules([home,roster,detail],ResearchRequest(extraction_mode='rules'))
        self.assertEqual(data['contacts'][0]['role'],'Partner')

    def test_single_person_profile_header_has_a_grounded_association(self):
        row = self.record('<h1>Jane Doe</h1><p>Managing Partner</p><a href="mailto:jane@example.com">Email Jane</a>')
        self.assertEqual(row.contacts[0].name, 'Jane Doe')
        self.assertEqual(row.contacts[0].association_status, 'sourced')

    def test_profile_does_not_reach_into_a_distant_footer(self):
        row = self.record('<h1>Jane Doe</h1><p>Partner</p><p>' + 'Biography text. ' * 60 + '</p><footer>other@example.com</footer>')
        self.assertIsNone(row.contacts[0].name)

    def test_name_and_email_can_be_sourced_while_role_stays_unknown(self):
        row = self.record('<h1>Jane Doe</h1><p>jane@example.com</p>')
        self.assertEqual(row.contacts[0].name, 'Jane Doe')
        self.assertIsNone(row.contacts[0].role)
        self.assertEqual(row.contacts[0].association_status, 'sourced')
        self.assertFalse(row.contacts[0].buyer_role_match)
        self.assertFalse(row.contacts[0].research_ready)

    def test_retired_partner_is_not_a_current_buyer(self):
        row = self.record('<title>Jane Doe — Example Law</title><h2>Jane Doe</h2><p>Retired Partner</p><p>jane@example.com</p>')
        self.assertEqual(row.contacts[0].role, 'Retired Partner')
        self.assertFalse(row.contacts[0].buyer_role_match)
        self.assertFalse(row.contacts[0].research_ready)

    def test_profile_secretary_address_does_not_replace_the_partners_address(self):
        row = self.record('<title>Jane Doe — Example Law</title><h2>Jane Doe</h2><p>Partner</p><p>jane@example.com</p><p>Legal Assistant:</p><h3>John Smith</h3><p>john@example.com</p>')
        contact = next(c for c in row.contacts if c.email == 'jane@example.com')
        self.assertEqual(contact.name, 'Jane Doe')
        assistant = next(c for c in row.contacts if c.email == 'john@example.com')
        self.assertIsNone(assistant.name)

    def test_published_named_contact_takes_priority_over_unassigned_inboxes(self):
        root = self.page('<p>' + ' '.join(f'office{i}@example.com' for i in range(50)) + '</p>')
        detail = self.page('<h1>Jane Doe</h1><p>Partner</p><p>jane@example.com</p>')
        output = extract_rules([root, detail], ResearchRequest(extraction_mode='rules'))
        self.assertEqual(len(output['contacts']), 50)
        self.assertTrue(any(c['name'] == 'Jane Doe' for c in output['contacts']))

    def test_neighboring_footer_address_is_not_assigned_to_a_person(self):
        row = self.record('<div class="team-member"><h2>Jane Doe</h2><p>Partner</p></div><footer>jane@example.com</footer>')
        self.assertIsNone(row.contacts[0].name)

    def test_profile_heading_cannot_assign_a_footer_address(self):
        row = self.record('<h1>Jane Doe</h1><p>Partner</p><footer>jane@example.com</footer>')
        self.assertIsNone(row.contacts[0].name)

    def test_ambiguous_multi_person_card_is_not_associated(self):
        row = self.record('<article><h2>Jane Doe</h2><p>Partner</p><h2>John Smith</h2><p>Founder</p><p>jane@example.com john@example.com</p></article>')
        self.assertTrue(all(c.name is None for c in row.contacts))

    def test_general_inbox_on_a_named_card_stays_a_firm_inbox(self):
        row = self.record('<div class="team-member"><h2>Jane Doe</h2><p>Partner</p><p>info@example.com</p></div>')
        self.assertIsNone(row.contacts[0].name)
        self.assertEqual(row.contacts[0].inbox_type, "generic")

    def test_third_party_schema_and_footer_are_not_firm_contacts(self):
        for changes in ({'email': 'jane@outside.example'}, {'url': 'https://outside.example/jane'}):
            node = {'@type': 'Person', 'name': 'Jane Doe', 'jobTitle': 'Partner', 'email': 'jane@example.com', **changes}
            row = self.record('<script type="application/ld+json">' + json.dumps(node) + '</script>')
            self.assertFalse(any(c.association_status == 'sourced' for c in row.contacts))

    def test_untrusted_card_payload_must_be_in_the_retrieved_page(self):
        page = self.page('<p>jane@example.com</p>')
        page['contact_blocks'] = ['Jane Doe\nPartner\njane@example.com']
        output = extract_rules([page], ResearchRequest(extraction_mode='rules'))
        self.assertIsNone(output['contacts'][0]['name'])

    def test_unified_free_credit_ledger_overrides_old_verification_capacity(self):
        request = ResearchRequest(extraction_mode='rules', spend_policy='free_allowance_only', budget_usd=0)
        source = SourceTools(request, RunBudget(request))
        for remaining in (0, True, None, -1):
            payload = {'data': {'plan_name': 'Free', 'requests': {'credits': {'remaining': remaining}, 'verifications': {'remaining': 99}}}}
            with patch.object(source, '_provider_json', return_value=(200, payload)):
                with self.assertRaises(SourceError):
                    source._require_free_allowance('hunter', 'test-only')


if __name__ == '__main__':
    unittest.main()
