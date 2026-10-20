import unittest
from unittest.mock import MagicMock

from shared.lexmom_email_transport import EmailTransportSettings, build_demo_notification, build_email_request, check_readiness


def settings(**changes):
    data = dict(region='us-east-1',identity_domain='example.com',mail_from_domain='bounces.example.com',
        from_address='hello@example.com',reply_to='support@example.org',demo_to='support@example.org',
        configuration_set='test-email-config',role_arn='arn:aws:iam::000000000000:role/TestEmailRole',
        events_queue_url='https://sqs.us-east-1.amazonaws.com/000000000000/test-events')
    return EmailTransportSettings(**{**data,**changes})


class TransportTests(unittest.TestCase):
    def test_missing_configuration_does_not_fall_back_to_shared_keys(self):
        with self.assertRaisesRegex(ValueError,'Missing email configuration'):
            EmailTransportSettings.from_env({'AWS_ACCESS_KEY_ID':'unrelated-placeholder'})

    def test_sender_domain_and_queue_scope_must_match(self):
        with self.assertRaises(ValueError): settings(from_address='hello@unrelated.example')
        with self.assertRaises(ValueError): settings(events_queue_url='https://sqs.us-west-2.amazonaws.com/000000000000/test-events')
        with self.assertRaises(ValueError): settings(events_queue_url='https://evil.example/test-events')

    def test_header_injection_is_rejected(self):
        with self.assertRaises(ValueError): settings(reply_to='support@example.org\r\nBcc: hidden@example.net')
        with self.assertRaises(ValueError): build_email_request(settings(),to='a@example.org',subject='Hi\r\nBcc:x',text='Hello')
        with self.assertRaises(ValueError): build_email_request(settings(),to='a@example.org,b@example.org',subject='Hi',text='Hello')

    def test_demo_destination_and_reply_identity_are_fixed_by_configuration(self):
        request=build_demo_notification(settings(),subject='Requested demo',text='Saved request')
        self.assertEqual(request['Destination']['ToAddresses'],['support@example.org'])
        self.assertEqual(request['ReplyToAddresses'],['support@example.org'])
        self.assertEqual(request['FromEmailAddress'],'hello@example.com')
        self.assertEqual(request['ConfigurationSetName'],'test-email-config')

    def test_bad_boolean_does_not_enable_sending(self):
        env = {'LEXMOM_EMAIL_AGENT_'+name:value for name,value in {'AWS_REGION':'us-east-1','IDENTITY_DOMAIN':'example.com',
            'MAIL_FROM_DOMAIN':'bounces.example.com','FROM':'hello@example.com','REPLY_TO':'support@example.org','DEMO_TO':'support@example.org',
            'CONFIGURATION_SET':'test-email-config','ROLE_ARN':'arn:aws:iam::000000000000:role/TestEmailRole',
            'EVENTS_QUEUE_URL':'https://sqs.us-east-1.amazonaws.com/000000000000/test-events','SEND_ENABLED':'yes'}.items()}
        with self.assertRaisesRegex(ValueError,'must be true or false'): EmailTransportSettings.from_env(env)

    def test_readiness_distinguishes_verified_setup_and_disabled_sending(self):
        session=MagicMock(); ses=MagicMock(); sqs=MagicMock()
        session.client.side_effect=lambda name,**kwargs: ses if name=='sesv2' else sqs
        ses.get_account.return_value={'ProductionAccessEnabled':True,'SendingEnabled':True,'EnforcementStatus':'HEALTHY'}
        ses.get_email_identity.return_value={'VerifiedForSendingStatus':True,'VerificationStatus':'SUCCESS',
            'DkimAttributes':{'Status':'SUCCESS','SigningEnabled':True},
            'MailFromAttributes':{'MailFromDomain':'bounces.example.com','MailFromDomainStatus':'SUCCESS','BehaviorOnMxFailure':'REJECT_MESSAGE'},
            'ConfigurationSetName':'test-email-config'}
        ses.get_configuration_set.return_value={'SendingOptions':{'SendingEnabled':False},'DeliveryOptions':{'TlsPolicy':'REQUIRE'},
            'SuppressionOptions':{'SuppressedReasons':['BOUNCE','COMPLAINT']}}
        ses.get_configuration_set_event_destinations.return_value={'EventDestinations':[{'Enabled':True,'MatchingEventTypes':['SEND','DELIVERY','BOUNCE','COMPLAINT'],
            'SnsDestination':{'TopicArn':'placeholder-topic'}}]}
        sqs.get_queue_attributes.return_value={'Attributes':{'SqsManagedSseEnabled':'true','RedrivePolicy':'{"deadLetterTargetArn":"arn:aws:sqs:us-east-1:000000000000:test-dlq","maxReceiveCount":5}','MessageRetentionPeriod':'1209600'}}
        result=check_readiness(settings(),session)
        self.assertTrue(result['setup_verified'])
        self.assertFalse(result['ses_sending_enabled_for_configuration'])
        self.assertFalse(result['runtime_send_enabled'])
        self.assertFalse(result['campaigns_enabled'])
        self.assertFalse(result['delivery_test_verified'])
        ses.send_email.assert_not_called(); sqs.receive_message.assert_not_called()
        ses.get_email_identity.return_value['DkimAttributes']['Status']='PENDING'
        self.assertFalse(check_readiness(settings(),session)['setup_verified'])


if __name__=='__main__': unittest.main()
