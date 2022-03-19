from decimal import Decimal
import boto3
import requests
import json
from datetime import datetime
import redis
from boto3.dynamodb.conditions import Key
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
dynamodb_client = None
cost_counter_table = None
SINGLE_UPSTREAM_QUERY_COST = 0.1

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
    global dynamodb_client
    dynamodb_client = boto3.resource('dynamodb',
                                     region_name='eu-centeral-1',
                                     aws_access_key_id="key",
                                     aws_secret_access_key="secert",
                                     endpoint_url="http://dynamodb:8000")

    try:
        dynamodb_client.create_table(
            TableName='cost_counter_table',
            KeySchema=[
                {
                    'AttributeName': 'name',
                    'KeyType': 'HASH'  # Partition key
                },
                {
                    'AttributeName': 'creation_time',
                    'KeyType': 'RANGE'
                }

            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'name',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'creation_time',
                    'AttributeType': 'S'
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 10,
                'WriteCapacityUnits': 10
            }
        )
    except Exception as err:
        print(err, flush=True)
    global cost_counter_table
    cost_counter_table = dynamodb_client.Table("cost_counter_table")
    cost_counter_table.put_item(Item={"name": "cost_reset", "creation_time": str(datetime.now().timestamp())})
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
    if False and quote:
        return json.loads(quote)
    else:
        response = requests.get('https://query1.finance.yahoo.com/v7/finance/quote?symbols='+symbol,
                                headers=headers)
        cost_counter_table.put_item(Item={"name": "cost", "creation_time": str(datetime.now().timestamp())})
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


@app.route('/get_cost')
def get_cost():
    scan = cost_counter_table.query(
        KeyConditionExpression=Key('name').eq('cost_reset')
    )
    last_rest_time = 0
    if len(scan['Items']):
        last_rest_time = scan['Items'][0]['creation_time']
    print(last_rest_time, flush=True)
    scan = cost_counter_table.query(
        KeyConditionExpression=Key('name').eq('cost') & Key('creation_time').gt(last_rest_time)
    )
    return str(len(scan['Items']) * round(SINGLE_UPSTREAM_QUERY_COST, 1))


@app.route('/reset_cost_counter')
def reset_cost_counter():
    scan = cost_counter_table.query(
        KeyConditionExpression=Key('name').eq('cost_reset')
    )
    with cost_counter_table.batch_writer() as batch:
        for item in scan['Items']:
            batch.delete_item(Key={'name': item['name'], 'creation_time': item['creation_time']})
    cost_counter_table.put_item(Item={"name": "cost_reset", "creation_time": str(datetime.now().timestamp())})
    return "reset done"


def calculate_cache_expiry(quote):
    if quote['marketState'] == "Regular":
        if int(quote['averageDailyVolume10Day']) > 1000000:
            return 10 * 60 * 1000
        else:
            return 20 * 60 * 1000
    else:
        return 60 * 60 * 1000


if __name__ == '__main__':
    app.run(host='0.0.0.0', port='5001')
    # serve(app, host="0.0.0.0", port=5001, threads=12)
