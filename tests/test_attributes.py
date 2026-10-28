import dataclasses
import pytest
from app.adjudicate import RULES, adjudicate
from app.catalog import CATEGORIES, Claim, ClaimType, count_subjects
from app.observation import Count, Defect, PhotoObservation


def verdict(kind='part_no_damage', subject='screen', value='', **kwargs):
    claim = Claim('c1', ClaimType(kind), 'Claim', subject, value)
    return adjudicate([claim], [PhotoObservation('p1', 'detail', True, **kwargs)])[0]


def test_catalogue_rules_exist_and_parameters_are_valid():
    assert len(CATEGORIES) == 5
    for attributes in CATEGORIES.values():
        for a in attributes:
            assert ClaimType(a['type']) in RULES
            if a['type'] in ('piece_count', 'part_no_damage'):
                assert a['subject']


def test_part_supported_only_when_explicitly_fully_visible():
    v = verdict(counts=(Count('screen', 1, True),))
    assert v.status == 'supported'
    assert v.photo_ids == ('p1',)


@pytest.mark.parametrize('counts', [(), (Count('phone', 1, True),),
    (Count('screen', 0, True),), (Count('screen', 1, False),), (Count('screen', 1, True, 0),)])
def test_unseen_or_partial_part_never_supported(counts):
    v = verdict(item='phone', counts=counts)
    assert v.status == 'inconclusive'
    assert 'screen' in v.request


def test_part_contradicted_by_located_defect_in_another_view():
    claim = Claim('c', ClaimType.PART_NO_DAMAGE, 'Screen has no visible damage', 'screen')
    obs = [PhotoObservation('p1', 'detail', True, counts=(Count('screen', 1, True),)),
           PhotoObservation('p2', 'front', True, defects=(Defect('crack', 'screen edge'),))]
    v = adjudicate([claim], obs)[0]
    assert v.status == 'contradicted'
    assert v.photo_ids == ('p2',)


def test_unrelated_damage_and_substring_do_not_contradict_part():
    assert verdict(counts=(Count('screen', 1, True),),
                   defects=(Defect('scratch', 'case'),)).status == 'supported'
    assert verdict(defects=(Defect('crack', 'sunscreen bottle'),)).status == 'inconclusive'
    assert verdict(counts=(Count('screen', 1, True),),
                   defects=(Defect('scratch', ''),)).status == 'inconclusive'


@pytest.mark.parametrize('text,expected', [('Samsung', 'supported'), (' SAMSUNG ', 'supported'),
    ('Samsung Galaxy', 'inconclusive'), ('Not Samsung', 'inconclusive'),
    ('Apple', 'inconclusive'), ('', 'inconclusive')])
def test_label_exact_text_only_no_unjustified_contradiction(text, expected):
    v = verdict('label_text', '', 'Samsung', visible_text=(text,))
    assert v.status == expected
    if expected == 'inconclusive':
        assert 'Samsung' in v.request


@pytest.mark.parametrize('kind,subject,value', [('part_no_damage','screen',''), ('label_text','','Samsung')])
def test_new_rules_need_usable_detail_and_request_specific_photo(kind, subject, value):
    claim = Claim('c', ClaimType(kind), 'Claim', subject, value)
    for observations in ([], [PhotoObservation('p', 'detail', False)]):
        v = adjudicate([claim], observations)[0]
        assert v.status == 'inconclusive'
        assert (subject or value) in v.request


def test_only_neutral_part_noun_sent_to_observer():
    assert count_subjects([Claim('c', ClaimType.PART_NO_DAMAGE, 'No cracks', 'screen'),
                           Claim('d', ClaimType.LABEL_TEXT, 'Label reads Samsung', value='Samsung')]) == ['screen']
