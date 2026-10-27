"""Public HTML extraction across layouts, with no network or paid providers."""
import unittest

from .models import ResearchRequest
from .public_site import information_links, public_observations


class PublicSiteTests(unittest.TestCase):
    def page(self, document):
        return {'url': 'https://firm.example/', 'retrieved_at': '2026-10-20T10:00:00+00:00',
                'document': document, 'text': '', 'links': []}

    def records(self, document):
        return public_observations(self.page(document), ResearchRequest(extraction_mode='rules', max_llm_calls=0))

    def test_people_without_email_survive_different_card_layouts(self):
        rows = self.records("<article><h3>Jane Example</h3><p>Managing Partner</p></article>"
                            "<section><div><strong>John Sample</strong><span>Attorney</span></div></section>")
        self.assertEqual({(row['name'], row['role']) for row in rows},
                         {('Jane Example', 'Managing Partner'), ('John Sample', 'Attorney')})
        self.assertTrue(all(row['email'] is None and not row['outreach_eligible'] for row in rows))

    def test_mailto_links_keep_association_inside_one_person_card(self):
        rows = self.records("<article><h3>Jane Example</h3><p>Partner</p><a href='mailto:jane@firm.example'>Email</a></article>"
                            "<article><h3>John Sample</h3><p>Attorney</p></article><footer>info@firm.example</footer>")
        jane = next(row for row in rows if row.get('name') == 'Jane Example')
        john = next(row for row in rows if row.get('name') == 'John Sample')
        self.assertEqual(jane['email'], 'jane@firm.example')
        self.assertIsNone(john['email'])
        self.assertIn('jane@firm.example', jane['evidence_excerpt'])
        self.assertFalse(any(row.get('name') and row.get('email') == 'info@firm.example' for row in rows))

    def test_external_mailbox_is_unassigned_and_generic_inbox_is_not_a_person(self):
        rows = self.records("<article><h3>Jane Example</h3><p>Partner</p><span>info@firm.example</span></article>"
                            "<p>Other company: help@external.example</p>")
        jane = next(row for row in rows if row.get('name') == 'Jane Example')
        self.assertIsNone(jane['email'])
        external = next(row for row in rows if row.get('email') == 'help@external.example')
        self.assertIsNone(external['firm'])
        self.assertIsNone(external['website'])

    def test_adjacent_people_never_share_one_role_or_email(self):
        rows = self.records("<section><div><h3>Jane Example</h3></div>"
                            "<div><h3>John Sample</h3><p>Partner</p><p>john@firm.example</p></div></section>")
        self.assertFalse(any(row.get('name') == 'Jane Example' for row in rows))
        self.assertEqual(next(row for row in rows if row.get('name') == 'John Sample')['email'], 'john@firm.example')

    def test_react_stream_segment_is_read_without_executing_script(self):
        rows = self.records('<template id="B:0"></template><div hidden id="S:0"><article>'
                            '<strong>Jane Example</strong><p>Attorney</p></article></div>'
                            '<script>$RC("B:0","S:0"); throw new Error("never execute");</script>')
        self.assertEqual([row['name'] for row in rows], ['Jane Example'])

    def test_unreferenced_hidden_css_and_script_content_are_not_contacts(self):
        rows = self.records('<div hidden id="S:0"><h3>Jane Example</h3><p>Partner jane@firm.example</p></div>'
                            '<div style="display: none!important"><h3>John Sample</h3><p>Attorney john@firm.example</p></div>'
                            '<script>"private@firm.example"</script><nav><h3>Example Company</h3><p>Partner</p></nav>')
        self.assertEqual(rows, [])

    def test_link_discovery_uses_paths_and_semantics_but_respects_navigation_bounds(self):
        page = self.page('<a href="/reach-us">Get in touch</a><a href="/team/jane">Jane</a>'
                         '<a href="/about" rel="nofollow">About</a><a href="/join">Contact us</a>'
                         '<a href="https://other.example/contact">Contact</a><a href="http://firm.example/contact">Contact</a>'
                         '<a href="/contact?token=private">Contact</a><a href="/contact" hidden>Contact</a>')
        self.assertEqual(set(information_links(page, page['url'])),
                         {'https://firm.example/reach-us', 'https://firm.example/team/jane'})

    def test_named_profile_link_can_have_an_arbitrary_path(self):
        page = self.page('<article><a href="/bio-jane"><h3>Jane Example</h3></a><p>Attorney</p></article>'
                         '<nav><a href="/misc">Member Area</a></nav>')
        self.assertEqual(information_links(page, page['url']), ['https://firm.example/bio-jane'])


if __name__ == '__main__':
    unittest.main()
