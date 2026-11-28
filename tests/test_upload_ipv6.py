import ipaddress
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'vendor')]
import app
from poc import dt_source


class LocalIPv6Tests(unittest.TestCase):
    def setUp(self):
        self.sock = Mock()
        self.sock.getsockname.return_value = ('192.0.2.1', 1234)
        self.adapters = {
            'Wi-Fi': [SimpleNamespace(family=socket.AF_INET, address='192.0.2.1')],
            'VPN': [SimpleNamespace(family=socket.AF_INET6, address='fe80::1%9')],
        }

    def test_reconnect_after_enabling_ipv6_on_the_selected_adapter(self):
        with patch('psutil.net_if_addrs', return_value=self.adapters):
            with self.assertRaises(dt_source.LocalIPv6Unavailable) as failure:
                dt_source.local_link_local(self.sock)
            event = json.dumps({'issue': 'local_ipv6', 'adapter': failure.exception.adapter})
            self.assertEqual(app.upload_network_hint('[network] ' + event),
                             {'code': 'local_ipv6', 'adapter': 'Wi-Fi', 'platform': sys.platform})
            self.adapters['Wi-Fi'].append(SimpleNamespace(family=socket.AF_INET6, address='fe80::2%5'))
            self.assertEqual(dt_source.local_link_local(self.sock), ipaddress.IPv6Address('fe80::2').packed)

    def test_retry_uses_another_address_and_keeps_it_on_reconnect(self):
        adapters = {'Wi-Fi': ['192.0.2.1', 'fe80::4%5', 'fe80::2%5'], 'VPN': ['fe80::1%9']}
        self.sock.getpeername.return_value = ('192.0.2.2', 41234)
        attempts = {}
        with patch.object(dt_source, 'adapter_addresses', return_value=adapters):
            for retry, expected in [(0, 'fe80::2'), (1, 'fe80::4'), (None, 'fe80::4'), (2, 'fe80::2')]:
                self.assertEqual(dt_source.select_link_local(self.sock, attempts, retry),
                                 ipaddress.IPv6Address(expected).packed)
            self.sock.getpeername.return_value = ('192.0.2.3', 52345)
            self.assertEqual(dt_source.select_link_local(self.sock, attempts), ipaddress.IPv6Address('fe80::2').packed)

    def test_windows_fallback_without_psutil_uses_only_the_connected_adapter(self):
        rows = [{"InterfaceAlias": "VPN", "IPAddress": "fe80::1"},
                {"InterfaceAlias": "家庭网络", "IPAddress": "192.0.2.1"}]
        with patch.dict(sys.modules, psutil=None), patch.object(sys, 'platform', 'win32'), \
                patch.dict(dt_source.os.environ, SystemRoot='C:/Windows'), \
                patch.object(dt_source.subprocess, 'run') as query:
            query.return_value.stdout = json.dumps(rows)
            with self.assertRaises(dt_source.LocalIPv6Unavailable) as failure:
                dt_source.local_link_local(self.sock)
            self.assertEqual(failure.exception.adapter, '家庭网络')
            rows.append({"InterfaceAlias": "家庭网络", "IPAddress": "fe80::2%5"})
            query.return_value.stdout = json.dumps(rows)
            self.assertEqual(dt_source.local_link_local(self.sock), ipaddress.IPv6Address('fe80::2').packed)
            query.side_effect = OSError('unavailable')
            with self.assertRaisesRegex(ValueError, 'could not read Windows network adapters'):
                dt_source.local_link_local(self.sock)

    def test_repeated_control_disconnects_then_data_connection(self):
        retry = ['[tcp] connection from console', '[compat] the PS5 asked for the newer console info',
                 '[cmd] session ended: connection closed after 0/24 bytes']
        lines = retry * 2 + ['[data] connection from console'] + retry * 2
        lines += ['GFP5 file complete', 'response complete cmd=0xb3', 'response complete cmd=0x94']
        with TemporaryDirectory() as directory, ExitStack() as stack:
            state = {'session': directory, 'console': {'hostId': 'id', 'host': 'example', 'firmware': '0'},
                     'title': 'test', 'user': {'name': 'example', 'id': '1'}, 'entryId': 1}
            stack.enter_context(patch.dict(app.STATE, state))
            stack.enter_context(patch.dict(app.JOB))
            for name in ('run_tool', 'prefix_path', 'relay', 'refused_key_request', 'log'):
                stack.enter_context(patch.object(app, name))
            stack.enter_context(patch.object(app.time, 'sleep'))
            stack.enter_context(patch.object(app, 'spawn', return_value=SimpleNamespace(stdout=lines)))
            stages = stack.enter_context(patch.object(app, 'stage'))
            app.job_upload()
        calls = stages.call_args_list
        warnings = [i for i, call in enumerate(calls) if (call.kwargs.get('hint') or {}).get('code') == 'ipv6_data_unreached']
        self.assertEqual(len(warnings), 1)
        self.assertTrue(any(call.args == ('console_connected',) and call.kwargs == {'hint': None}
                            for call in calls[warnings[0]+1:]))
        self.assertEqual(calls[-1].args, ('uploaded',))

    def test_unknown_interface_and_unrelated_messages(self):
        with patch('psutil.net_if_addrs', return_value={}):
            with self.assertRaises(dt_source.LocalIPv6Unavailable) as failure:
                dt_source.local_link_local(self.sock)
            self.assertIsNone(failure.exception.adapter)
        for line in ('[cmd] session ended: timed out', '[network] invalid', '[network] {}'):
            self.assertIsNone(app.upload_network_hint(line))
