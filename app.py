import requests
import json
from datetime import datetime
import redis
from flask import Flask, jsonify
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
# from waitress import serve
import logging
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)

app = Flask(__name__)
auth = HTTPBasicAuth()
redis_client = None

api_users = {
    "exquote": generate_password_hash("exquotepass")
}


@auth.verify_password
def verify_password(username, password):
    if username in api_users and \
            check_password_hash(api_users.get(username), password):
        return username


@app.route('/')
def health_check():
    return jsonify("running")


@app.route('/init')
def init():
    global redis_client
    redis_client = redis.Redis(host='redis', port=6379, decode_responses=True, password='sOmE_sEcUrE_pAsS')
    redis_client.mset({"Croatia": "Zagreb", "Bahamas": "Nassau"})
    print(redis_client.get("Bahamas"), flush=True)
    return jsonify("init done")


@app.route('/get_quote/<string:symbol>/')
def get_quote(symbol):
    if ',' in symbol:
        return "Error! please query one symbol at a time"
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 '
                      'Safari/537.36',
    }
    quote = redis_client.get(symbol)
    if quote:
        return json.loads(quote)
    else:
        response = requests.get('https://query1.finance.yahoo.com/v7/finance/quote?symbols='+symbol,
                                headers=headers)
        results = json.loads(response.text)['quoteResponse']['result']
        if not results:
            return "Error! unknown symbol"
        full_quote = results[0]
        quote = {
            "symbol": full_quote['symbol'],
            "update_time": datetime.now().strftime("%m/%d/%Y %H:%M:%S"),
            "exchange": full_quote['exchange'],
            "shortName": full_quote['shortName'],
            "price": full_quote['regularMarketPrice'],
            "currency": full_quote['currency'],
            "change_percent": full_quote['regularMarketChangePercent']
        }
        redis_client.mset({symbol: json.dumps(quote)})
        redis_client.pexpire(symbol, calculate_cache_expiry(full_quote))
        return quote


def calculate_cache_expiry(quote):
    if quote['marketState'] is "Regular":
        if int(quote['averageDailyVolume10Day']) > 1000000:
            return 10 * 60 * 1000
        else:
            return 20 * 60 * 1000
    else:
        return 60 * 60 * 1000


if __name__ == '__main__':
    app.run(host='0.0.0.0', port='5001')
    # serve(app, host="0.0.0.0", port=5001, threads=12)
