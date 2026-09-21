"""Regression checks for the final, fixed ordinal research configuration."""
from copy import deepcopy
import json

import pytest
from streamlit.testing.v1 import AppTest

from src.experiment import run_experiment
from src.explanation import build_explanation
from src.models import ROOT, Model, load_cases, load_model, read_json
from src.p2_format import format_p2
from src.risks import evaluate_risks
from src.user_cases import UserCase, build_user_model, configuration_identity, load_property_catalog


PROPERTIES = {'independent_component_deployment', 'single_deployment_unit'}


def requirement(prop, expected=True):
    return {'name': next(p['name'] for p in load_property_catalog() if p['property'] == prop),
            'property': prop, 'operator': '==', 'required_value': expected}


def test_final_matrix_scale_and_properties_are_exact():
    model = load_model()
    assert [c['id'] for c in model.criteria] == [f'K{i}' for i in range(1, 7)]
    assert all(c['direction'] == 'maximize' for c in model.criteria)
    assert [[a['ratings'][f'K{i}']['value'] for i in range(1, 7)] for a in model.architectures] == [
        [2, 1, 2, 5, 5, 4], [4, 4, 5, 3, 3, 3], [5, 5, 4, 2, 2, 2]]
    assert all(r['status'] == 'confirmed' for a in model.architectures for r in a['ratings'].values())
    assert [a['properties'] for a in model.architectures] == [
        {'independent_component_deployment': False, 'single_deployment_unit': True},
        {'independent_component_deployment': True, 'single_deployment_unit': False},
        {'independent_component_deployment': True, 'single_deployment_unit': False}]
    catalog = load_property_catalog()
    assert {p['property'] for p in catalog} == PROPERTIES
    assert all(p['type'] == 'boolean' for p in catalog)
    assert {c['property'] for c in model.constraints} == PROPERTIES
    assert all(c['type'] == 'boolean' and c['enabled'] is False for c in model.constraints)
    criteria = read_json(ROOT / 'config/criteria.json')
    assert criteria['scale'] == {
        '1': 'выраженно неблагоприятное положение альтернативы по критерию',
        '2': 'неблагоприятное положение', '3': 'промежуточное / смешанное положение',
        '4': 'преимущество', '5': 'выраженное преимущество'}
    assert 'не является расчётом полной стоимости владения' in model.criteria[5]['description']
    assert len(load_cases()) == 10


@pytest.mark.parametrize('prop,expected,feasible', [
    ('independent_component_deployment', True, {'A2', 'A3'}),
    ('independent_component_deployment', False, {'A1'}),
    ('single_deployment_unit', True, {'A1'}),
    ('single_deployment_unit', False, {'A2', 'A3'}),
])
def test_boolean_values_mean_exact_requirement(prop, expected, feasible):
    model = build_user_model(UserCase({f'K{i}': 1 for i in range(1, 7)}, [requirement(prop, expected)]))
    result = build_explanation(model)
    assert {r['architecture'] for r in result.ranking} == feasible
    assert {r['architecture'] for r in result.excluded_alternatives} == {'A1', 'A2', 'A3'} - feasible
    text = '\n'.join(format_p2(result)['exclusion_texts'])
    assert ('«Да»' if expected else '«Нет»') in text
    assert prop not in text


@pytest.mark.parametrize('architecture_id', ['A1', 'A2', 'A3'])
@pytest.mark.parametrize('risk_index', range(6))
@pytest.mark.parametrize('value,triggered', [(1, True), (2, True), (2.01, False), (5, False)])
def test_each_risk_uses_its_criterion_and_inclusive_threshold(architecture_id, risk_index, value, triggered):
    model = load_model()
    assert len(read_json(ROOT / 'config/risks.json')['risks']) == 6
    assert len(model.risks) == 18
    rule = next(r for r in model.risks if r['id'] == f'R{risk_index + 1}_{architecture_id}')
    assert rule['criterion'] == f'K{risk_index + 1}'
    assert rule['operator'] == '<=' and rule['threshold'] == 2
    arch = next(a for a in model.architectures if a['id'] == rule['architecture'])
    values = {a['id']: {k: 5 for k in a['ratings']} for a in model.architectures}
    values[arch['id']][rule['criterion']] = value
    ratings = deepcopy(arch['ratings'])
    ratings[rule['criterion']]['value'] = value
    found = evaluate_risks(arch['id'], model.risks, values, ratings)
    assert [r['id'] for r in found] == ([rule['id']] if triggered else [])


@pytest.mark.parametrize('criterion,winner,risks', [('K4', 'A1', ['R1', 'R2', 'R3']),
                                                    ('K3', 'A2', []), ('K1', 'A3', ['R4', 'R5', 'R6'])])
def test_risks_only_belong_to_recommended_architecture(criterion, winner, risks):
    model = load_model()
    for c in model.criteria:
        c['weight'] = int(c['id'] == criterion)
    result = build_explanation(model)
    assert result.recommended_architecture == winner
    assert [r['id'].split('_')[0] for r in result.risks] == risks
    assert all(r['architecture'] == winner for r in result.risks)


def test_conflicting_requirements_in_ui_do_not_produce_recommendation():
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    app.radio(key='work_mode').set_value('Пользовательский кейс').run()
    app.button(key='add_constraint').click().run()
    app.button(key='add_constraint').click().run()
    app.selectbox(key='user_property_2').set_value('single_deployment_unit').run()
    app.button(key='calculate_user').click().run()
    assert not app.exception
    result = app.session_state['result']
    assert result.status == 'no_feasible'
    assert result.recommended_architecture is None and result.ranking == []
    assert len(result.excluded_alternatives) == 3
    assert len(result.input_snapshot['constraints']) == 2
    assert all(c['expected'] for c in result.input_snapshot['constraints'])
    assert any('ни одна из рассматриваемых архитектур' in w.value for w in app.warning)
    for mode in ('P1', 'P2', 'P3'):
        app.radio(key='presentation_mode').set_value(mode).run()
        assert not app.exception
        assert app.session_state['result'].calculation_id == result.calculation_id
    assert len(app.get('download_button')) == 2
    assert not app.get('data_editor')


def test_experiment_snapshot_contains_exact_configuration_and_replays(tmp_path):
    output = tmp_path / 'experiment.csv'
    frame = run_experiment(output=output)
    snapshot = read_json(tmp_path / 'experiment_config_snapshot.json')
    assert snapshot['model_config_id'] == configuration_identity()['model_config_id']
    for name in ('architectures', 'criteria', 'constraints', 'risks'):
        assert snapshot['configuration'][name] == read_json(ROOT / 'config' / f'{name}.json')
    assert snapshot['model_cases'] == read_json(ROOT / 'data/example_cases.json')
    assert set(frame['model_config_id']) == {snapshot['model_config_id']}
    assert set(frame['config_snapshot']) == {'experiment_config_snapshot.json'}
    records = json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
    for record in records:
        saved = record['explanation']
        assert build_explanation(Model(**saved['input_snapshot'])).to_dict() == saved
    assert frame['validation_passed'].all() and len(frame) == 10


@pytest.mark.parametrize('status', ['estimated', 'missing'])
def test_soa_risk_uses_case_rating_even_though_baseline_is_above_threshold(status):
    model = load_model()
    for criterion in model.criteria:
        criterion['weight'] = int(criterion['id'] == 'K3')
    model.architectures[1]['ratings']['K1'] = ({'value': 2, 'status': status}
        if status == 'estimated' else {'value': None, 'status': status, 'model_value': 2})
    result = build_explanation(model)
    assert result.recommended_architecture == 'A2'
    assert [r['id'] for r in result.risks] == ['R1_A2']
    assert result.risks[0]['data_status'] == status
    assert result.risks[0]['model_value_used'] == (status == 'missing')
