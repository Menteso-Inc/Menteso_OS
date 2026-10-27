import pytest
from agents.pct_agent import contact_policy as policy


@pytest.mark.parametrize('dns,retained',[
    ('mx',True),('implicit_mx',True),('unconfirmed',True),('nxdomain',False),('null_mx',False)])
def test_routing_uncertainty_preserves_verified_source_but_known_invalid_dns_does_not(monkeypatch,dns,retained):
    monkeypatch.setattr(policy,'email_domain_status',lambda email:dns)
    result={'emails':['main@example.org'],'additional_emails':[{
        'email':'extra@example.org','role':'agent','owner':'Example'}]}
    issues=policy.apply_email_routing(result,'original_crop_and_ocr_agreement')
    assert bool(result['emails']) is retained and bool(result['additional_emails']) is retained
    assert all(check['domain']==dns and check['mailbox']=='not_tested' for check in result['email_checks'].values())
    if dns=='unconfirmed':assert issues==['Email source verified; mail routing could not be confirmed']*2


def test_routing_check_cannot_create_an_email_that_failed_source_verification(monkeypatch):
    monkeypatch.setattr(policy,'email_domain_status',lambda email:pytest.fail('No verified email to check'))
    result={'emails':[],'additional_emails':[]}
    assert policy.apply_email_routing(result,'original_crop_and_ocr_agreement')==[]
    assert result['emails']==[]
