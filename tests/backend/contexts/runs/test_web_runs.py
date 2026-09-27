import ast
import functools
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch
import pytest
from backend.interfaces.cli import web
from backend.contexts.runs.application.web_runs import WebRuns
from backend.contexts.runs.domain.errors import RunBusyError, RunRequestError
from backend.contexts.constraints.infrastructure.constraints_io import (
    constraints_from_json,
    constraints_hash,
    constraints_to_json,
)
from backend.contexts.schedule.domain.canonical import canonicalize
from backend.contexts.schedule.domain.schedule import (
    Availability,
    ControlEvent,
    EventKind,
    OperatingStatus,
    Role,
    Schedule,
    ScheduleMeta,
    WellState,
)
from backend.shared.hashing import canonical_bytes

WEB_SOURCE = Path(web.__file__)


def _write_source_run(root: Path, run_id: str = 'plan-1') -> Path:
    run_dir = root / run_id
    (run_dir / 'inputs').mkdir(parents=True)
    (run_dir / 'schedule').mkdir()
    constraints = constraints_from_json({})
    (run_dir / 'inputs' / 'constraints.json').write_text(
        json.dumps(constraints_to_json(constraints)), encoding='utf-8'
    )
    (run_dir / 'manifest.json').write_text(
        json.dumps({'constraints_hash': constraints_hash(constraints), 'sound': True}),
        encoding='utf-8',
    )
    (run_dir / 'economics').mkdir()
    (run_dir / 'economics' / 'result.json').write_text(
        json.dumps({'npv_methodology': 1234.0}), encoding='utf-8'
    )
    schedule = canonicalize(Schedule(
        meta=ScheduleMeta(n_control_dates=4, n_intervals=3, wells=('13',)),
        initial_state={
            '13': WellState(
                availability=Availability.AVAILABLE,
                role=Role.PROD,
                operating_status=OperatingStatus.OPEN,
                setpoint=100.0,
            )
        },
        fixed_deck_events=(),
        control_events=(ControlEvent(0, '13', EventKind.SET_LRAT, 100.0),),
    ))
    (run_dir / 'schedule' / 'schedule.json').write_bytes(canonical_bytes(schedule))
    return run_dir


def test_fixed_action_draft_preserves_source_and_reports_scope_and_cost(tmp_path: Path) -> None:
    _write_source_run(tmp_path)
    runs = WebRuns(tmp_path)

    draft = runs.draft_alternative({
        'source_run_id': 'plan-1',
        'well': '13',
        'control_step': 1,
        'target_m3_per_day': 75,
    })

    assert draft['action'] == {
        'kind': 'producer-liquid-rate-target',
        'well': '13',
        'from_step': 1,
        'through_step': 2,
        'original_target_m3_per_day': 100.0,
        'alternative_target_m3_per_day': 75.0,
        'constraints_changed': False,
        'policy_reoptimized': False,
    }
    assert draft['source_run_id'] == 'plan-1'
    assert draft['source_schedule_hash'] != draft['alternative_schedule_hash']
    assert draft['constraints_hash'] == constraints_hash(constraints_from_json({}))
    assert draft['source_npv_rub'] == 1234.0
    assert draft['additional_opm_evaluations'] == 1
    assert runs.list() == []


@pytest.mark.parametrize('payload', [
    {'source_run_id': '../plan-1', 'well': '13', 'control_step': 1, 'target_m3_per_day': 75},
    {'source_run_id': 'missing', 'well': '13', 'control_step': 1, 'target_m3_per_day': 75},
])
def test_fixed_action_draft_rejects_untrusted_or_missing_run(tmp_path: Path, payload: dict[str, Any]) -> None:
    _write_source_run(tmp_path)
    with pytest.raises(RunRequestError):
        WebRuns(tmp_path).draft_alternative(payload)


def test_fixed_action_draft_rejects_manifest_constraints_mismatch(tmp_path: Path) -> None:
    source = _write_source_run(tmp_path)
    (source / 'manifest.json').write_text(
        json.dumps({'constraints_hash': '0' * 64, 'sound': True}), encoding='utf-8'
    )
    with pytest.raises(RunRequestError, match='do not match'):
        WebRuns(tmp_path).draft_alternative({
            'source_run_id': 'plan-1',
            'well': '13',
            'control_step': 1,
            'target_m3_per_day': 75,
        })


def test_confirmed_fixed_action_is_persisted_and_idempotent(tmp_path: Path) -> None:
    _write_source_run(tmp_path)
    runs = WebRuns(tmp_path)
    preview = runs.draft_alternative({
        'source_run_id': 'plan-1',
        'well': '13',
        'control_step': 1,
        'target_m3_per_day': 75,
    })
    request = {
        'request_id': 'alternative-123',
        'source_run_id': 'plan-1',
        'well': '13',
        'control_step': 1,
        'target_m3_per_day': 75,
        'source_manifest_hash': preview['source_manifest_hash'],
        'source_economics_hash': preview['source_economics_hash'],
        'source_schedule_hash': preview['source_schedule_hash'],
        'alternative_schedule_hash': preview['alternative_schedule_hash'],
        'constraints_hash': preview['constraints_hash'],
    }
    with patch('backend.contexts.runs.application.web_runs.threading.Thread') as thread:
        started = runs.start({'mode': 'alternative', 'alternative_request': request})
        repeated = runs.start({'mode': 'alternative', 'alternative_request': request})

    assert started['mode'] == 'alternative'
    assert started['alternative_request'] == request
    assert repeated['run_id'] == started['run_id']
    assert (tmp_path / started['run_id'] / 'constraints.json').is_file()
    thread.return_value.start.assert_called_once()


def test_confirmed_fixed_action_rejects_stale_preview(tmp_path: Path) -> None:
    _write_source_run(tmp_path)
    runs = WebRuns(tmp_path)
    preview = runs.draft_alternative({
        'source_run_id': 'plan-1',
        'well': '13',
        'control_step': 1,
        'target_m3_per_day': 75,
    })
    with pytest.raises(RunRequestError, match='changed after preview'):
        runs.start({
            'mode': 'alternative',
            'alternative_request': {
                'request_id': 'alternative-123',
                'source_run_id': 'plan-1',
                'well': '13',
                'control_step': 1,
                'target_m3_per_day': 75,
                'source_manifest_hash': preview['source_manifest_hash'],
                'source_economics_hash': preview['source_economics_hash'],
                **{**preview, 'source_schedule_hash': 'stale'},
            },
        })
    assert runs.list() == []


def test_search_freezes_constraints_and_rejects_concurrent_run(tmp_path):
    jobs = WebRuns(tmp_path)
    with patch('backend.contexts.runs.application.web_runs.threading.Thread') as thread:
        run = jobs.start({'constraints': {'injection_limits': {'2007': 30000}}, 'budget': 10})
        saved = json.loads((tmp_path / run['run_id'] / 'constraints.json').read_text(encoding='utf-8'))
        assert saved['injection_limits'] == {'2007': 30000}
        assert run['status'] == 'running'
        thread.return_value.start.assert_called_once()
        with pytest.raises(RunBusyError):
            jobs.start({'constraints': {}, 'budget': 10})


def test_case_request_is_persisted_and_confirmation_is_idempotent(tmp_path):
    jobs = WebRuns(tmp_path)
    metadata = {'request_id': 'draft-123', 'request': 'Остановить скважину 13', 'scenario': 'base'}
    with patch('backend.contexts.runs.application.web_runs.threading.Thread') as thread:
        run = jobs.start({'constraints': {}, 'budget': 10, 'case_request': metadata})
        repeated = jobs.start({'constraints': {}, 'budget': 10, 'case_request': metadata})
    assert repeated['run_id'] == run['run_id']
    assert repeated['case_request'] == metadata
    saved = json.loads((tmp_path / run['run_id'] / 'job.json').read_text(encoding='utf-8'))
    assert saved['case_request'] == metadata
    thread.return_value.start.assert_called_once()


def test_conversational_case_confirms_exact_preview_and_restores_by_request(tmp_path):
    jobs = WebRuns(tmp_path)
    base = {'injection_limits': {'2007': 30000}}
    proposed = {'injection_limits': {'2007': 12000}}
    metadata = {
        'request_id': 'jarvis-draft-1',
        'request': 'Установи лимит закачки 12000 м3/сут в 2007 году',
        'scenario': 'base',
        'base_constraints': base,
    }
    with patch.object(jobs, 'draft', return_value={'constraints': proposed}) as draft:
        with pytest.raises(RunRequestError, match='differ from the reviewed case draft'):
            jobs.start({'constraints': base, 'budget': 10, 'case_request': metadata})
        assert jobs.by_request_id(metadata['request_id']) is None
        with patch('backend.contexts.runs.application.web_runs.threading.Thread'):
            run = jobs.start({'constraints': proposed, 'budget': 10, 'case_request': metadata})
            repeated = jobs.start({'constraints': proposed, 'budget': 10, 'case_request': metadata})
        assert repeated['run_id'] == run['run_id']
        restored = jobs.by_request_id(metadata['request_id'])
        assert restored is not None
        assert restored['run_id'] == run['run_id']
        with pytest.raises(RunRequestError, match='already used for another case'):
            jobs.start({'constraints': base, 'budget': 10, 'case_request': {
                'request_id': metadata['request_id'], 'request': metadata['request'], 'scenario': 'base'
            }})
        assert draft.call_count >= 2


def test_request_lookup_rejects_invalid_identifier(tmp_path):
    with pytest.raises(RunRequestError, match='request_id is invalid'):
        WebRuns(tmp_path).by_request_id('../other')


def test_invalid_case_request_metadata_never_starts_job(tmp_path):
    jobs = WebRuns(tmp_path)
    for metadata in (
        {'request_id': '../bad', 'request': 'test', 'scenario': 'base'},
        {'request_id': 'draft-1', 'request': '', 'scenario': 'base'},
    ):
        with pytest.raises(RunRequestError):
            jobs.start({'constraints': {}, 'case_request': metadata})
    assert jobs.list() == []


def test_bad_infrastructure_never_starts_job(tmp_path):
    jobs = WebRuns(tmp_path)
    for infrastructure in ({'compensation_min': .8}, {'unknown': 10}, {'water_supply_unlimited': True, 'external_water_m3_per_day': 1}):
        with pytest.raises(RunRequestError):
            jobs.start({'constraints': {'infrastructure': infrastructure}})
    assert jobs.list() == []
    assert not jobs.lock.locked()


def test_verify_rejects_traversal_and_missing_plan(tmp_path):
    jobs = WebRuns(tmp_path)
    for run_id in ('../../escape', 'web-missing'):
        with pytest.raises(RunRequestError):
            jobs.start({'mode': 'verify', 'run_id': run_id})
    assert not jobs.lock.locked()


def test_failed_worker_is_not_a_verified_result(tmp_path):
    jobs = WebRuns(tmp_path)
    directory = tmp_path / 'web-test'
    directory.mkdir()
    jobs.lock.acquire()
    data = {'run_id': 'web-test', 'status': 'running'}
    with patch('backend.contexts.runs.infrastructure.worker_process.subprocess.Popen') as run:
        run.return_value.poll.return_value = 1
        run.return_value.returncode = 1
        jobs._execute(directory, data, 'verify', 30)
    result = jobs.list()[0]
    assert result['status'] == 'failed'
    assert 'manifest' not in result
    assert not jobs.lock.locked()


def test_cancel_marks_running_job_and_signals_worker(tmp_path):
    jobs = WebRuns(tmp_path)
    with patch('backend.contexts.runs.application.web_runs.threading.Thread'):
        run = jobs.start({'constraints': {}, 'budget': 10})
    result = jobs.cancel(run['run_id'])
    assert result['cancel_requested'] is True
    assert result['status'] == 'running'
    assert jobs._cancel_events[run['run_id']].is_set()


def test_completed_job_cannot_be_overwritten_by_a_late_cancel(tmp_path):
    jobs = WebRuns(tmp_path)
    with patch('backend.contexts.runs.application.web_runs.threading.Thread'):
        run = jobs.start({'constraints': {}, 'budget': 10})
    directory = tmp_path / run['run_id']
    saved = jobs.store.read(directory)
    saved.update(status='completed', message='done')
    jobs.store.write(directory, saved)
    with pytest.raises(RunRequestError):
        jobs.cancel(run['run_id'])
    assert jobs._cancel_events[run['run_id']].is_set() is False


def test_cancelled_worker_is_recorded_as_cancelled(tmp_path):
    from backend.contexts.runs.infrastructure.worker_process import WORKER_CANCELLED
    jobs = WebRuns(tmp_path)
    directory = tmp_path / 'web-cancelled'
    directory.mkdir()
    cancellation = threading.Event()
    cancellation.set()
    jobs.lock.acquire()
    data = {'run_id': 'web-cancelled', 'status': 'running'}
    with patch('backend.contexts.runs.application.web_runs.run_worker', return_value=WORKER_CANCELLED):
        jobs._execute(directory, data, 'search', 10, cancellation)
    result = jobs.list()[0]
    assert result['status'] == 'cancelled'
    assert result['message_key'] == 'runs.status.cancelled'
    assert not jobs.lock.locked()


def test_worker_cancellation_terminates_the_worker_process_group(tmp_path):
    from backend.contexts.runs.infrastructure.worker_process import WORKER_CANCELLED, run_worker
    cancellation = threading.Event()
    cancellation.set()
    process = type('Process', (), {'pid': 1234, 'poll': lambda self: None, 'wait': lambda self, **kwargs: -15})()
    with patch('backend.contexts.runs.infrastructure.worker_process.subprocess.Popen', return_value=process), \
         patch('backend.contexts.runs.infrastructure.worker_process.os.killpg') as killpg:
        result = run_worker(tmp_path, 'search', 10, cancel_event=cancellation)
    assert result == WORKER_CANCELLED
    killpg.assert_called_once()
    process_group, signal_number = killpg.call_args.args
    assert process_group == process.pid
    assert signal_number == 15


def test_importing_adapter_does_not_mark_active_jobs_failed(tmp_path):
    directory = tmp_path / 'web-active'
    directory.mkdir()
    path = directory / 'job.json'
    path.write_text(json.dumps({'run_id': 'web-active', 'status': 'running'}), encoding='utf-8')
    jobs = WebRuns(tmp_path)
    assert json.loads(path.read_text(encoding='utf-8'))['status'] == 'running'
    jobs.recover_interrupted()
    assert json.loads(path.read_text(encoding='utf-8'))['status'] == 'failed'


def test_opm_progress_comes_from_real_log_and_keeps_model_date(tmp_path):
    directory = tmp_path / 'web-progress'
    output = directory / 'opm/runs/opm-one'
    output.mkdir(parents=True)
    (directory / 'job.json').write_text(json.dumps({'run_id': 'web-progress', 'status': 'running', 'mode': 'verify'}), encoding='utf-8')
    (output / 'flow.log').write_text('Report step 17/371 at day 400/12511, date = 01-Jan-2007\n')
    assert WebRuns(tmp_path).list()[0]['progress'] == {'step': 17, 'total': 371, 'date': '01.01.2007'}


def test_running_search_projects_worker_progress(tmp_path):
    directory = tmp_path / 'web-search-progress'
    directory.mkdir()
    (directory / 'job.json').write_text(json.dumps({
        'run_id': 'web-search-progress', 'status': 'running', 'mode': 'search'
    }), encoding='utf-8')
    (directory / 'search-progress.json').write_text(json.dumps({
        'stage': 'fallback', 'step': 4, 'total': 10
    }), encoding='utf-8')
    assert WebRuns(tmp_path).list()[0]['progress'] == {
        'stage': 'fallback', 'step': 4, 'total': 10
    }


@pytest.fixture()
def server(tmp_path, monkeypatch) -> Iterator[str]:
    (tmp_path / 'index.html').write_text('<!doctype html><title>aios</title>', encoding='utf-8')
    monkeypatch.setattr(web.SpaRequestHandler, 'runs', WebRuns(tmp_path / 'runs'))
    (tmp_path / 'runs').mkdir()
    handler = functools.partial(web.SpaRequestHandler, directory=str(tmp_path))
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[0], httpd.server_address[1]
    try:
        yield f'http://{host}:{port}'
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def fetch(url: str, body: dict[str, Any] | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(url)
    if body is not None:
        request.data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        request.method = 'POST'
        request.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def test_handler_declares_every_method_once() -> None:
    tree = ast.parse(WEB_SOURCE.read_text(encoding='utf-8'))
    handler = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef) and node.name == 'SpaRequestHandler')
    names = [node.name for node in handler.body if isinstance(node, ast.FunctionDef)]
    assert sorted(names) == sorted(set(names))
    assert names.count('do_GET') == 1
    assert names.count('do_POST') == 1


def test_get_runs_returns_the_run_list(server: str) -> None:
    status, body = fetch(f'{server}/api/runs')
    assert status == 200
    assert json.loads(body)['runs'] == []


def test_get_run_by_conversation_request_restores_saved_job(server: str) -> None:
    root = web.SpaRequestHandler.runs.root
    folder = root / 'web-conversation'
    folder.mkdir()
    (folder / 'job.json').write_text(json.dumps({
        'run_id': 'web-conversation', 'status': 'running', 'mode': 'search',
        'case_request': {'request_id': 'jarvis-123', 'request': 'case', 'scenario': 'base'},
    }), encoding='utf-8')

    status, body = fetch(f'{server}/api/runs/by-request/jarvis-123')
    assert status == 200
    assert json.loads(body)['run_id'] == 'web-conversation'
    missing, _ = fetch(f'{server}/api/runs/by-request/unknown')
    assert missing == 404
    invalid, _ = fetch(f'{server}/api/runs/by-request/bad%20id')
    assert invalid == 400


def test_post_runs_reaches_the_adapter(server: str) -> None:
    with patch.object(web.SpaRequestHandler.runs, 'start', return_value={'run_id': 'web-test', 'status': 'running'}) as start:
        status, body = fetch(f'{server}/api/runs', {'constraints': {}, 'budget': 10})
    assert status not in (404, 405)
    assert status == 202
    assert json.loads(body)['run_id'] == 'web-test'
    start.assert_called_once()


def test_post_fixed_action_draft_reaches_the_adapter(server: str) -> None:
    preview = {'source_run_id': 'plan-1', 'opm_evaluations': 2}
    with patch.object(
        web.SpaRequestHandler.runs,
        'draft_alternative',
        return_value=preview,
    ) as draft:
        status, body = fetch(
            f'{server}/api/cases/alternative',
            {
                'source_run_id': 'plan-1',
                'well': '13',
                'control_step': 1,
                'target_m3_per_day': 75,
            },
        )
    assert status == 200
    assert json.loads(body) == preview
    draft.assert_called_once()


def test_post_case_draft_returns_preview_without_starting_job(server: str) -> None:
    constraints = {
        'injection_limits': {},
        'liquid_limits': {},
        'production_floors': {},
        'oil_limits': {},
        'watercut_limits': {},
        'well_outages': [],
        'infrastructure': {},
    }
    status, body = fetch(
        f'{server}/api/cases/draft',
        {
            'request': 'Остановить скважину 13 с 01.02.2010 по 01.03.2010',
            'constraints': constraints,
            'scenario': 'base',
        },
    )
    draft = json.loads(body)

    assert status == 200
    assert draft['operation'] == 'add_well_outage'
    assert draft['well'] == '13'
    assert draft['date_from'] == '2010-02-01'
    assert draft['date_to'] == '2010-03-01'
    assert draft['constraints']['well_outages'] == [
        {'well': '13', 'control_step_from': draft['control_step_from'], 'control_step_to': draft['control_step_to']}
    ]
    assert web.SpaRequestHandler.runs.list() == []


def test_delete_run_requests_cancellation(server: str) -> None:
    request = urllib.request.Request(f'{server}/api/runs/web-test', method='DELETE')
    with patch.object(web.SpaRequestHandler.runs, 'cancel', return_value={'run_id': 'web-test', 'cancel_requested': True}) as cancel:
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 202
            assert json.loads(response.read())['cancel_requested'] is True
    cancel.assert_called_once_with('web-test')


def test_case_draft_api_rejects_invalid_request_without_creating_a_job(server: str) -> None:
    status, body = fetch(
        f'{server}/api/cases/draft',
        {'request': 'make a new limit', 'constraints': {}, 'scenario': 'base'},
    )

    assert status == 400
    assert 'error' in json.loads(body)
    assert web.SpaRequestHandler.runs.list() == []


def test_unknown_post_is_json_not_method_not_allowed(server: str) -> None:
    status, body = fetch(f'{server}/api/nowhere', {'anything': True})
    assert status == 404
    assert 'error' in json.loads(body)


def test_jarvis_path_goes_to_the_proxy(server: str) -> None:
    def reply(handler: Any) -> None:
        handler._json(200, {'ok': True})

    with patch('backend.interfaces.cli.web.forward', side_effect=reply) as forward:
        status, body = fetch(f'{server}/api/jarvis/health')
    assert status == 200
    assert json.loads(body) == {'ok': True}
    forward.assert_called_once()


def test_unknown_spa_route_falls_back_to_index(server: str) -> None:
    status, body = fetch(f'{server}/some/spa/route')
    assert status == 200
    assert b'<title>aios</title>' in body
