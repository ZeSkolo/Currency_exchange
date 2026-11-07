import unittest, tempfile, json, urllib.error
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch, MagicMock
from core import run, rate_for, connect

class Tests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'app.db')
        self.input = {'action': 'convert', 'amount': '100', 'base': 'USD', 'quote': 'INR', 'mode': 'demo'}

    def tearDown(self):
        self.tmp.cleanup()

    def test_demo_explicit(self):
        r = run(self.input)['result']
        self.assertEqual(r['converted'], '8300.00')
        self.assertEqual(r['source'], 'FICTIONAL DEMO')
        self.assertTrue(r['stale'])

    def test_decimal_exactness(self):
        self.assertEqual(run(dict(self.input, amount='0.10'))['result']['converted'], '8.30')

    def test_fee(self):
        r = run(dict(self.input, fee_percent='2', fixed_fee='1'))['result']
        self.assertEqual(r['net_source'], '97')
        self.assertEqual(r['converted'], '8051.00')

    def test_same_currency(self):
        self.assertEqual(run(dict(self.input, quote='USD'))['result']['converted'], '100.00')

    def test_jpy(self):
        self.assertEqual(run(dict(self.input, quote='JPY', amount='1.001'))['result']['converted'], '150')

    def test_nan_inf_negative(self):
        for value in ['NaN', 'Infinity', '-1', '0', '1e2', ' 100 ', '1,000']:
            with self.assertRaises(ValueError):
                run(dict(self.input, amount=value))

    def test_invalid_currency(self):
        with self.assertRaises(ValueError):
            run(dict(self.input, quote='INVALID'))

    def test_large_fee(self):
        with self.assertRaises(ValueError):
            run(dict(self.input, fixed_fee='100'))

    def test_budget(self):
        r = run(dict(self.input, action='budget', items=[{'name': 'Hotel', 'amount': '20'}, {'name': 'Food', 'amount': '10'}]))['result']
        self.assertEqual(r['converted'], '2490.00')
        self.assertEqual(len(r['breakdown']), 2)

    def test_bad_budget(self):
        with self.assertRaises(ValueError):
            run(dict(self.input, action='budget', items=[]))

    def test_history(self):
        run(self.input, self.db)
        self.assertEqual(len(run({}, self.db)['history']), 1)

    def test_no_silent_demo_fallback(self):
        with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('offline')):
            with self.assertRaisesRegex(ValueError, 'no cached'):
                run(dict(self.input, mode='live'), self.db)

    def test_live_provider_and_cache(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"date":"2026-11-06","base":"USD","quote":"INR","rate":84.123456789}'
        with patch('urllib.request.urlopen', return_value=response) as call:
            run(dict(self.input, mode='live'), self.db)
            run(dict(self.input, mode='live'), self.db)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[0].full_url, 'https' + '://' + 'api.frankfurter.dev/v2/rate/usd/inr')

    def test_stale_cache(self):
        db = connect(self.db)
        db.execute('INSERT INTO cache VALUES(?,?,?,?)', ('USD/INR', '83.123456789', '2026-01-02', 0))
        db.commit()
        with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('offline')):
            r = rate_for('USD', 'INR', 'live', db, 1800000000)
            self.assertTrue(r['stale'])
            self.assertIn('stale cache', r['source'])
        db.close()

    def test_bad_provider_pair(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"date":"2026-11-06","base":"EUR","quote":"INR","rate":84}'
        with patch('urllib.request.urlopen', return_value=response):
            with self.assertRaises(ValueError):
                run(dict(self.input, mode='live'), self.db)
