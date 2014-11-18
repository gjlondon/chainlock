"""
Flask Documentation:     http://flask.pocoo.org/docs/
Jinja2 Documentation:    http://jinja.pocoo.org/2/documentation/
Werkzeug Documentation:  http://werkzeug.pocoo.org/documentation/

This file creates your application.

Basic project skeleton/template taken from: git@github.com:zachwill/flask_heroku.git
"""

import json

import flask
from flask.ext.heroku import Heroku
import os
from flask import Flask, render_template, request
from flask.ext.sqlalchemy import SQLAlchemy
from block_io import BlockIo
import boto.sns


app = Flask(__name__)
heroku = Heroku(app)
db = SQLAlchemy(app)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'this_should_be_configured')
app.config['aws_access_key_id'] = os.environ.get('aws_access_key_id')
app.config['aws_secret_access_key'] = os.environ.get('aws_secret_access_key')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'this_should_be_configured')
app.config['BLOCKIO_API_KEY'] = os.environ.get('BLOCKIO_API_KEY', '')

REGION = 'us-east-1'
sns_conn = boto.sns.connect_to_region(REGION,
                                  aws_access_key_id=app.config['aws_access_key_id'],
                                  aws_secret_access_key=app.config['aws_secret_access_key'],
                                  )

if os.environ.get('HEROKU') is not None:
    import logging
    stream_handler = logging.StreamHandler()
    app.logger.addHandler(stream_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('chainlock startup')

###
# MODELS
###


class BTCTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_address = db.Column(db.VARCHAR)
    to_address = db.Column(db.VARCHAR)
    amount = db.Column(db.FLOAT)
    confirmed = db.Column(db.BOOLEAN, default=False)
    cleared = db.Column(db.BOOLEAN, default=False)

    def __init__(self, from_address, to_address, amount):
        self.from_address = from_address
        self.to_address = to_address
        self.amount = amount

    def __repr__(self):
        return 'Transaction from {} to {} for {} BTC'.format(self.from_address, self.to_address, self.amount)


###
# Routing for your application.
###

@app.route('/')
def home():
    """Render website's home page."""
    return render_template('home.html')


@app.route('/about/')
def about():
    """Render the website's about page."""
    return render_template('about.html')


@app.route('/api/initiate', methods=['POST'])
def initiate_transaction():
    """
    Receive the initial request to send bitcoin to an address and generate the
    push notification to solicit the transaction confirmation
    """

    target_address = request.args.get("send_to")
    amount = request.args.get("amount")
    from_address = request.form.get("from_address", "2MygS9Wmdm9qT4pGaNN1nv4fy64vpYTHZCd")
    transaction = BTCTransaction(from_address, target_address, amount)
    db.session.add(transaction)
    db.session.commit()
    TARGET_ARN="arn:aws:sns:us-east-1:569388847635:endpoint/APNS_SANDBOX/chainlock-sns-test/410d844a-897f-3364-b7f1-207ca0b5b0a8"
    message = """You've requested to send {} BTC. Please confirm with Nymi.""".format(amount,
                                                                                      target_address,)
    apns_dict = {'aps': {'alert': message,
                         'sound': 'default',},
                 "id": transaction.id,
                 "random_thing": "grrrrr8"
    }
    apns_string = json.dumps(apns_dict, ensure_ascii=False)
    message_payload = {'default': 'default message', 'APNS_SANDBOX': apns_string}
    message_json = json.dumps(message_payload, ensure_ascii=False)
    response = {
        'status': 200,
        'message': "transaction {} initiated. confirmation pending.".format(transaction.id)
    }
    try:
        publication = sns_conn.publish(target_arn=TARGET_ARN,
                                       message=message_json,
                                       message_structure='json')
    except Exception as e:
        app.logger.error(e)
        response = {
            'status': 500,
            'message': e.message
        }

    return flask.jsonify(**response)

@app.route('/api/confirm', methods=['POST'])
def confirm_transaction():
    """
    Receive the secret pin from the iphone client and actually carry out the transaction

    :return: json
    """
    try:
        transaction_id = request.args.get("transaction_id")
        secret_pin = request.args.get("secret_pin")
        transaction_queryset = db.session.query(BTCTransaction).filter(BTCTransaction.id == transaction_id)
        transaction = transaction_queryset.first()
        version = 2 # API version
        api_key = app.config["BLOCKIO_API_KEY"]
        api_key = "1d2d-9788-d71f-c73f"
        block_io = BlockIo(api_key, secret_pin, version)
        block_io.withdraw(amounts=transaction.amount,
                          to_addresses=transaction.to_address,
                          from_addresses=transaction.from_address)
        response = {
            "status": 200,
            "message": "transaction succeeded"
        }
    except Exception as e:
       app.logger.error(e)
       response = {
           "status": 500,
           "message": e.message,
       }
    return flask.jsonify(**response)


###
# The functions below should be applicable to all Flask apps.
###

@app.route('/<file_name>.txt')
def send_text_file(file_name):
    """Send your static text file."""
    file_dot_text = file_name + '.txt'
    return app.send_static_file(file_dot_text)


@app.after_request
def add_header(response):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to cache the rendered page for 10 minutes.
    """
    response.headers['X-UA-Compatible'] = 'IE=Edge,chrome=1'
    response.headers['Cache-Control'] = 'public, max-age=600'
    return response


@app.errorhandler(404)
def page_not_found(error):
    """Custom 404 page."""
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run(debug=True)

