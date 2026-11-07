"""Decimal-based reference-rate and travel-budget conversion, never money movement."""
import datetime as dt, json, sqlite3, time, urllib.request, urllib.error, re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
CURRENCIES = {'USD': 'US dollar', 'EUR': 'Euro', 'INR': 'Indian rupee', 'GBP': 'British pound', 'JPY': 'Japanese yen', 'AUD': 'Australian dollar', 'CAD': 'Canadian dollar', 'SGD': 'Singapore dollar', 'CHF': 'Swiss franc'}
DEMO = {k: Decimal(v) for k, v in {'USD': '1', 'EUR': '0.90', 'INR': '83.00', 'GBP': '0.78', 'JPY': '150.00', 'AUD': '1.50', 'CAD': '1.35', 'SGD': '1.34', 'CHF': '0.88'}.items()}

def number(value, label, minimum=Decimal('0'), maximum=Decimal('1000000000000')):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)) or len(str(value)) > 32:
        raise ValueError(label + ' must be a plain decimal string')
    if not re.fullmatch('[0-9]+(?:\\.[0-9]+)?', str(value)):
        raise ValueError(label + ' must be a plain decimal without separators or exponent')
    try:
        n = Decimal(value)
    except InvalidOperation:
        raise ValueError(label + ' must be a valid decimal')
    if not n.is_finite() or n < minimum or n > maximum:
        raise ValueError(label + ' is outside the supported range')
    if n.as_tuple().exponent < -6:
        raise ValueError(label + ' supports at most six decimal places')
    return n

def currency(code):
    if not isinstance(code, str) or code not in CURRENCIES:
        raise ValueError('Unsupported currency')
    return code

def connect(path):
    if path != ':memory:':
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript('CREATE TABLE IF NOT EXISTS cache(pair TEXT PRIMARY KEY,rate TEXT,rate_date TEXT,fetched REAL);CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY,created TEXT,base TEXT,quote TEXT,amount TEXT,converted TEXT,rate TEXT,rate_date TEXT,source TEXT);')
    return db

def rate_for(base, quote, mode, db, now=None):
    now = time.time() if now is None else now
    if mode not in ['demo', 'live']:
        raise ValueError('Choose demo or live rates')
    if base == quote:
        return {'rate': Decimal('1'), 'date': dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat(), 'source': 'same-currency identity', 'stale': False, 'notice': 'No exchange rate is needed for the same currency.'}
    if mode == 'demo':
        return {'rate': DEMO[quote] / DEMO[base], 'date': '2026-01-02', 'source': 'FICTIONAL DEMO', 'stale': True, 'notice': 'Fictional demonstration rates — not current, not market data and not usable for financial decisions.'}
    pair = base + '/' + quote
    cached = db.execute('SELECT * FROM cache WHERE pair=?', (pair,)).fetchone()
    network_error = False
    if cached and now - cached['fetched'] < 3600:
        rate = Decimal(cached['rate'])
        date = cached['rate_date']
        source = 'Frankfurter cached reference'
    else:
        try:
            url = 'https' + '://' + 'api.frankfurter.dev/v2/rate/' + base.lower() + '/' + quote.lower()
            request = urllib.request.Request(url, headers={'User-Agent': 'AhwanCurrencyPlanner/1.0', 'Accept': 'application/json'})
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read(64001)
                if len(raw) > 64000:
                    raise ValueError('Provider response exceeded limit')
                result = json.loads(raw, parse_float=Decimal)
            if not isinstance(result, dict):
                raise ValueError('Provider JSON object required')
            if result.get('base') != base or result.get('quote') != quote:
                raise ValueError('Provider returned a different pair')
            rate = Decimal(str(result.get('rate')))
            if not rate.is_finite() or not Decimal('0.0000000001') <= rate <= Decimal('1000000000'):
                raise ValueError('Invalid provider rate')
            date = dt.date.fromisoformat(result['date']).isoformat()
            source = 'Frankfurter reference'
            with db:
                db.execute('INSERT INTO cache VALUES(?,?,?,?) ON CONFLICT(pair) DO UPDATE SET rate=excluded.rate,rate_date=excluded.rate_date,fetched=excluded.fetched', (pair, str(rate), date, now))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, InvalidOperation):
            if not cached:
                raise ValueError('Live rates unavailable and no cached rate exists. Choose the explicitly labeled demo, or retry later.')
            rate = Decimal(cached['rate'])
            date = cached['rate_date']
            source = 'Frankfurter stale cache'
            network_error = True
    age = (dt.datetime.fromtimestamp(now, dt.timezone.utc).date() - dt.date.fromisoformat(date)).days
    return {'rate': rate, 'date': date, 'source': source, 'stale': network_error or age > 4, 'notice': 'Daily reference/mid-market data, not an executable bank quote. Bank spreads, fees and holidays may differ.' + (' Cached rate may be stale; refresh before decisions.' if network_error or age > 4 else '')}

def history(db):
    return [dict(row) for row in db.execute('SELECT * FROM history ORDER BY id DESC LIMIT 12')]

def run(payload, db_path=None):
    db = connect(db_path or ':memory:')
    try:
        action = payload.get('action', 'list')
        if action == 'list':
            return {'currencies': CURRENCIES, 'history': history(db), 'notice': 'No trades, transfers, wallets or financial advice. Demo rates are fictional.'}
        if action not in ['convert', 'budget']:
            raise ValueError('Unknown action')
        base = currency(payload.get('base', 'USD'))
        quote = currency(payload.get('quote', 'INR'))
        mode = payload.get('mode', 'demo')
        items = []
        if action == 'budget':
            raw = payload.get('items')
            if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
                raise ValueError('Budget requires 1–20 line items')
            for item in raw:
                if not isinstance(item, dict) or not isinstance(item.get('name'), str) or (not 1 <= len(item['name'].strip()) <= 60):
                    raise ValueError('Each budget item needs a name of 1–60 characters')
                items.append({'name': item['name'].strip(), 'amount': number(item.get('amount'), 'Item amount', Decimal('0.000001'))})
            amount = sum((x['amount'] for x in items))
            if amount > Decimal('1000000000000'):
                raise ValueError('Budget total is too large')
        else:
            amount = number(payload.get('amount'), 'Amount', Decimal('0.000001'))
        percent = number(payload.get('fee_percent', '0'), 'Fee percent', maximum=Decimal('20'))
        fixed = number(payload.get('fixed_fee', '0'), 'Fixed fee')
        fee = amount * percent / 100 + fixed
        if fee >= amount:
            raise ValueError('Fees must be less than the source amount')
        r = rate_for(base, quote, mode, db)
        quant = Decimal('1') if quote == 'JPY' else Decimal('0.01')
        net = amount - fee
        converted = (net * r['rate']).quantize(quant, rounding=ROUND_HALF_UP)
        result = {'base': base, 'quote': quote, 'amount': str(amount), 'rate': str(r['rate']), 'rate_date': r['date'], 'source': r['source'], 'stale': r['stale'], 'notice': r['notice'], 'fee_source': str(fee.quantize(Decimal('0.000001'))), 'net_source': str(net), 'converted': str(converted), 'gross_converted': str((amount * r['rate']).quantize(quant, rounding=ROUND_HALF_UP)), 'breakdown': [{'name': x['name'], 'source_amount': str(x['amount']), 'gross_converted': str((x['amount'] * r['rate']).quantize(quant, rounding=ROUND_HALF_UP))} for x in items]}
        with db:
            db.execute('INSERT INTO history(created,base,quote,amount,converted,rate,rate_date,source) VALUES(?,?,?,?,?,?,?,?)', (dt.datetime.now(dt.timezone.utc).isoformat(), base, quote, str(amount), str(converted), str(r['rate']), r['date'], r['source']))
        return {'result': result, 'history': history(db)}
    finally:
        db.close()
