# stock-exchange-quote

The service query Yahoo finance to retrieve stock exchange quote.
It is planned to run as a container on AWS

To run the service use:
  
   docker-compose -f docker-compose-dev.yml up

For initialization use:

  http://0.0.0.0:5001/init

for dev purposes on local machine use also the request below for creating a dynamodb table

  http://0.0.0.0:5001/init_dev


Service API:

To query sotck exchange quote use

  http://0.0.0.0:5001/get_quote/<symbol>
  

To check the cost of upstream requests to Yahoo since last reset use:
  
  http://0.0.0.0:5001/get_cost
  
To reset the cost calculator use:
  
  http://0.0.0.0:5001/reset_cost_counter
  
  
  
Notes:
  The service was planned to work in large scale
  Multiple copies of the container may be executed in parallel as far as they all talk with the same reids and dynamodb instances
  A purge function for the dynamodb table data should be run with a schedualer (schedualer is not implemented)
  For purging the table manually use: http://0.0.0.0:5001/purge_cost_counter


