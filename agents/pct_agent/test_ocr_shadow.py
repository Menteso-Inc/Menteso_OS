from agents.pct_agent.ocr_shadow import candidate


def test_email_can_never_skip_independent_image_verification():
    assert not candidate('email', [{'text': 'a@example.org'}], 'windows_en',
                         {'text': 'a@example.org', 'score': 1})


def test_same_ocr_engine_and_multiline_fields_are_ineligible():
    line = {'text': 'Example GmbH'}
    reading = {'text': line['text'], 'score': 1}
    assert not candidate('name', [line], 'rapidocr', reading)
    assert not candidate('name', [line, line], 'windows_en', reading)


def test_confident_disagreement_and_low_confidence_both_fall_back():
    lines = [{'text': '+49 123 456'}]
    assert not candidate('phone', lines, 'windows_en', {'text': '+49 123 458', 'score': 1})
    assert not candidate('phone', lines, 'windows_en', {'text': '+49 123 456', 'score': .8})
    assert candidate('phone', lines, 'windows_en', {'text': '+49 123 456', 'score': .999})
