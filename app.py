import boto3
import requests
import json
from datetime import datetime
import redis
from boto3.dynamodb.conditions import Key
from flask import Flask, jsonify

app = Flask(__name__)
redis_client = None
dynamodb_client = None
cost_counter_table = None
SINGLE_UPSTREAM_QUERY_COST = 0.1


@app.route('/')
def health_check():
    return jsonify("running")


# initializes the redis and dynamodb clients and resets upstream requests counter
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
    global cost_counter_table
    cost_counter_table = dynamodb_client.Table("cost_counter_table")
    # cost_counter_table.put_item(Item={"name": "cost_reset", "creation_time": str(datetime.now().timestamp())})
    return jsonify("init done")


# For dev env only creates a dynamodb table
@app.route('/init_dev')
def init_dev():
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
    return "init dev done"


# Get a quote by its symbol
@app.route('/get_quote/<string:symbol>/')
def get_quote(symbol):
    if ',' in symbol:
        return "Error! please query one symbol at a time"
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 '
                      'Safari/537.36'
    }
    quote = redis_client.get(symbol)
    if quote:
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


# Calculate the upstream requests cost since last reset
@app.route('/get_cost')
def get_cost():
    last_reset_time = get_newest_reset_counter_time()
    if not last_reset_time:
        last_reset_time = "0"
    scan = cost_counter_table.query(
        KeyConditionExpression=Key('name').eq('cost') & Key('creation_time').gt(last_reset_time)
    )
    count = len(scan['Items']) * SINGLE_UPSTREAM_QUERY_COST
    return str(round(count, 1))


# Add an object to counter table the resets the cost counter
@app.route('/reset_cost_counter')
def reset_cost_counter():
    cost_counter_table.put_item(Item={"name": "cost_reset",
                                      "creation_time": str(datetime.now().timestamp())})
    return "reset done"


# meant to be executed by a scheduler to purge old reset counters objs
@app.route('/purge_cost_counter')
def purge_cost_counter():
    reset_counter = get_newest_reset_counter_time()
    if not reset_counter:
        return
    scan = cost_counter_table.query(
        KeyConditionExpression=Key('name').eq('cost_reset') & Key('creation_time').lt(reset_counter)
    )
    with cost_counter_table.batch_writer() as batch:
        for item in scan['Items']:
            batch.delete_item(Key={'name': item['name'], 'creation_time': item['creation_time']})
    scan = cost_counter_table.query(
        KeyConditionExpression=Key('name').eq('cost') & Key('creation_time').lt(reset_counter)
    )
    with cost_counter_table.batch_writer() as batch:
        for item in scan['Items']:
            batch.delete_item(Key={'name': item['name'], 'creation_time': item['creation_time']})
    return "purge done"


def get_newest_reset_counter_time():
    scan = cost_counter_table.query(
        KeyConditionExpression=Key('name').eq('cost_reset'),
        ScanIndexForward=False,
        Limit=1
    )
    if len(scan['Items']):
        return scan['Items'][0]['creation_time']
    return None


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
