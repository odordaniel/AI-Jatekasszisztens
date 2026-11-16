"""Bounded audio text API responses and shared model discovery."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import test_settings_navigation as support


@unittest.skipUnless(support.QT_AVAILABLE, 'Qt UI dependencies are not installed')
class AudioAPITests(unittest.TestCase):
    setUpClass = classmethod(support.SettingsNavigationTests.setUpClass.__func__)

    def setUp(self):
        self.body_reads = []
        self.worker = self.audio.LiveWorker('key', 'https://example.com', 'stt', 'device',
            Path(self.temp.name) / 'recovery.json', 'https://example.com/v1/chat/completions',
            'text-key', 'primary', 'fallback')

    def response(self, content='Fordítás', status=200):
        response = Mock(status_code=status, is_redirect=False)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = [json.dumps({'choices': [{'message': {'content': content}}]}).encode()]
        # Reading response.text defeats stream=True, including for HTTP errors.
        def read_body(_):
            self.body_reads.append(True)
            return 'private-body'
        type(response).text = property(read_body)
        return response

    def translate(self, responses):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.post.side_effect = responses
        with patch.object(self.audio.requests, 'Session', return_value=session):
            result = self.worker._translate_sync('Source')
        return result, session

    def test_http_error_falls_back_without_reading_body(self):
        failed = self.response(status=500)
        result, session = self.translate([failed, self.response()])
        self.assertEqual(result, ('Fordítás', 'fallback'))
        failed.iter_content.assert_not_called()
        self.assertEqual(self.body_reads, [])
        self.assertFalse(session.trust_env)

    def test_null_result_does_not_save_literal_none(self):
        result, _ = self.translate([self.response(None), self.response('Good')])
        self.assertEqual(result, ('Good', 'fallback'))

    def test_oversize_response_falls_back(self):
        response = self.response()
        response.iter_content.return_value = [b'x' * (256 * 1024 + 1)]
        self.assertEqual(self.translate([response, self.response()])[0][1], 'fallback')

    def test_redirect_is_rejected_before_body_read(self):
        response = self.response()
        response.is_redirect = True
        self.translate([response, self.response()])
        response.iter_content.assert_not_called()

    def test_invalid_url_never_contacts_server(self):
        self.worker.translate_url = 'https:///chat/completions'
        with patch.object(self.audio.requests, 'Session') as session:
            with self.assertRaises(ValueError):
                self.worker._translate_sync('Source')
            session.assert_not_called()

    def test_caddy_ca_uses_configured_appdata(self):
        ca = self.core.ROOT / 'caddy-root.crt'
        ca.write_text('synthetic-ca')
        self.addCleanup(lambda: ca.unlink(missing_ok=True))
        self.worker.translate_url = 'https://test.home.arpa/v1/chat/completions'
        _, session = self.translate([self.response()])
        self.assertEqual(session.post.call_args.kwargs['verify'], str(ca))

    def test_http_failure_does_not_expose_server_body(self):
        with self.assertRaises(RuntimeError) as error:
            self.translate([self.response(status=500), self.response(status=503)])
        self.assertNotIn('private-body', str(error.exception))
        self.assertEqual(self.body_reads, [])

    def test_cancelled_session_does_not_start_fallback_request(self):
        response = self.response(status=503)
        def cancel_then_enter():
            self.worker.abort()
            return response
        response.__enter__.side_effect = cancel_then_enter
        with self.assertRaisesRegex(RuntimeError, 'megszakítva'):
            self.translate([response])

    def test_model_discovery_uses_bounded_shared_parser(self):
        worker = self.audio.TextModels('https://example.com/v1/chat/completions', 'key')
        found = []
        worker.loaded.connect(found.append)
        with patch.object(self.core, 'fetch_available_models', return_value=['models/b', 'a']):
            worker.run()
        self.assertEqual(found, [['a', 'b']])
