# Globals #


from bson.errors import InvalidId
from bson.objectid import ObjectId
from flask import Flask, jsonify, request, json, abort
from flask_pymongo import PyMongo
import http.client
import urllib.request
import urllib.parse
import urllib.error
import collections
# import base64
import hashlib
import requests

DEBUG = True

app = Flask(__name__)

app.config['MONGO_DBNAME'] = 'typesensedb'
app.config['MONGO_URI'] = 'mongodb://localhost:27017/typesensedb'

mongo = PyMongo(app)

"""
DATA MODEL
Collections: users, connections, conversations
Users: {"_id": ObjectId("..."), "fb_id": "...", "email": "...", "password": "...", "connections": [ObjectId("..."), ...]}
Connections: {"_id": ObjectId("..."), "fb_id": "...", "conversations": {ObjectId("..."): ObjectId("..."), ...}}
Conversations: {"_id": ObjectId("..."), "messages": [{"Hash": {"Sentiment": 0, "Author": "..."}}, ...]}
"""


# Helpers #

def analyze_sentiment(messages_list):
	"""Takes an ordered list of dictionaries in format: [ { "author" : "", "message" : "" }, ...]
	and returns dictionary in format: { "Hash": {"Sentiment" : 0, "Author" : "..."}, ...}
    Normalized sentiment values scaled between -1 and 1. Uses Azure sentiment analysis API."""

	# https://github.com/MicrosoftDocs/azure-docs/blob/master/articles/cognitive-services/text-analytics/how-tos/text-analytics-how-to-sentiment-analysis.md

    # Add dummy values to be able to calculate the impact on sentiment of all messages
	messages_list.insert(0, {"author": "dummy_author0", "message": " "})
	messages_list.insert(0, {"author": "dummy_author1", "message": " "})
	messages_list.insert(0, {"author": "dummy_author2", "message": " "})

	merged_messages = [(messages_list[i].get("message") + " " + messages_list[i+1].get("message") + " " + messages_list[i+2].get(
	    "message"), messages_list[i+2].get("author"), messages_list[i+2].get("message")) for i in range(len(messages_list) - 2)]

	message_sentiments = []

	for message in merged_messages:
		message_combo, author, last_message = message[0], message[1], message[2]
		# Encode string as bytes before hashing w/ SHA1
		last_message_hash = hashlib.sha1(str.encode(last_message)).hexdigest()

		# Get normalized sentiment (between -1.0 and 1.0) score for each message combo.
		normalized_sentiment_impact = sentiment_api_request(message_combo)
		message_sentiments.extend((last_message_hash, normalized_sentiment_impact, author))

	# Isolate sentiment impact of each message
	sentiment_change = [message_sentiments[i][1] - message_sentiments[i-1][1]
	    for i in range(len(message_sentiments))[1:]]
	messages_sentiment_impact = zip(message_sentiments[0], sentiment_change, message_sentiments[2])

    # message_sentiment_impact in format: [(last_message_hash, change in sentiment of last message, author), ...]
    # return list in format: [{"Hash": {"Sentiment" : 0, "Author" : "..."}}, ...]

	return [{item[0]:{"Sentiment": item[1], "Author": item[2]}} for item in message_sentiment_impact]


def sentiment_api_request(message):
	"""Make request to Azure Sentiment API with text. Returns normalized sentiment score (between -1 and 1)"""

	# https://westus.dev.cognitive.microsoft.com/docs/services/TextAnalytics.V2.0/operations/56f30ceeeda5650db055a3c9
	# https://docs.microsoft.com/en-us/azure/cognitive-services/text-analytics/how-tos/text-analytics-how-to-sentiment-analysis
	# https://github.com/MicrosoftDocs/azure-docs/blob/master/articles/cognitive-services/text-analytics/how-tos/text-analytics-how-to-sentiment-analysis.md

	subscription_key = "0d67adf8bc524458ab03de128db96426"
	api_endpoint = 'https://westcentralus.api.cognitive.microsoft.com/text/analytics/v2.0/sentiment'

    # Request headers
	headers = {
    	'Content-Type': 'application/json',
    	'Ocp-Apim-Subscription-Key': subscription_key
    }

	values = {"documents":
    	[
    		{
    			"language": "en",
    			"id"      : "1",
    			"text"    : message
    		}
    	]
    }

	response = requests.post(api_endpoint, data=json.dumps(values), headers=headers).text
	sentiment_score = json.loads(response)["documents"][0]["score"]
	# Normalization
	return (sentiment_score - 0.5) * 2


# Routing #


@app.route("/")
def main():
    """Default response; returns an error code."""
    return 404


@app.route("/TypeSense/api/create_user", methods=["POST"])
def create_user():
    """Creates a new user document; also checks if email already exists. Payload
    format: {'email': '...', 'password': '...', 'fb_id': '...'}."""
    if not request.json or not "email" in request.json:
        abort(400, "new_user(): request.json does not exist or does not contain 'email'")

    for user in mongo.db.users.find():
        if user["email"] == request.json["email"]:
            return jsonify({"registered": False})

    user_id = mongo.db.users.insert({
        "email": request.json["email"],
        "password": request.json["password"],  # NOTE: Password is stored insecurely
        "fb_id": request.json["fb_id"],
        "connections": []
    })

    return jsonify({"registered": True})


@app.route("/TypeSense/api/validate_user", methods=["POST"])
def validate_user():
    """Checks if login credentials are valid. Payload format: {'email': '...',
    'password': '...'}."""
    if not request.json or not "email" in request.json:
        abort(400, "check_user(): request.json does not exist or does not contain 'email'")

    for user in mongo.db.users.find():
        if user["email"] == request.json["email"] and u["password"] == request.json["password"]:
            return jsonify({"logged_in": True})

    return jsonify({"logged_in": False})


@app.route("/TypeSense/api/change_conversation", methods=["POST"])
def change_conversation():
    """Handles a conversation change. Returns sentiment scores for the new conversation's
    most recent messages. Payload format: {'email': '...', 'fb_id': '...',
    'messages': [{'author': True, 'message': '...'}, ...]}."""
    if not request.json or not "fb_id" in request.json:
        abort(400, "new_connection(): request.json does not exist or does not contain 'fb_id'")

    user = mongo.db.users.find_one({"email": request.json["email"]})
    messages = analyze_sentiment(request.json["messages"])

    for cxn in mongo.db.connections.find():
        # Connection exists
        if cxn["fb_id"] == request.json["fb_id"]:
            for user_cxn in user["connections"]:
                # Connection already has a conversation open with user
                connection = mongo.db.connections.find_one({"_id": ObjectId(str(user_cxn))})
                if connection["fb_id"] == request.json["fb_id"]:
                    conversation = mongo.db.conversations.find_one({"_id": connection["Conversations"][str(user["_id"])]})["Messages"]

                    db_hashes = [message_hash for message_hash in list(conversation.keys())]

                    payload_hashes = [{hashlib.sha1(str.encode(message["message"])).hexdigest(): message["message"]} for message in request.json["messages"]]

                    filtered_messages = [payload_hashes[message] for message in payload_hashes.keys() if message not in all_hashes]

                    analysis_input = [message for message in request.json["messages"] if message["message"] in filtered_messages]
                    analyzed_messages = analyze_sentiment(analysis_input)

                    final_messages = (conversation + analyzed_messages)
                    final_messages = final_messages[len(final_messages) - 20:]

                    mongo.db.conversations.insert(
                        {"_id": connection["Conversations"][str(user["_id"])]},
                        {"messages": final_messages}
                    )

                    return jsonify({"messages": final_messages})
            conversation = mongo.db.conversations.insert({"messages": messages})
            connection = mongo.db.connections.update(
                {"fb_id": cxn["fb_id"]},
                {"$set": {"conversations" + str(user["_id"]): str(conversation["_id"])}}
            )
            mongo.db.users.update({
                {"fb_id": user["fb_id"]},
                {"$push": {"connections": ObjectId(str(connection["_id"]))}}
            })

            return jsonify({"messages": messages})

    # Connection doesn't exist
    connection = mongo.db.connections.insert({
        "fb_id": request.json["fb_id"],
        "conversations": {str(user["_id"]): str(conversation["_id"])}
    })
    mongo.db.users.update({
        {"fb_id": user["fb_id"]},
        {"$push": {"connections": ObjectId(str(connection["_id"]))}}
    })

    return jsonify({"messages": messages})


@app.route("/TypeSense/api/new_message", methods=["POST"])
def new_message():
    return


# Error Handling #


def error_print(status_code, error):
    if DEBUG:
        print("------------")
        print("ERROR (" + str(status_code) + "): " + error)
        print("------------")


@app.errorhandler(400)
def bad_request(error):
    error_print(400, error.description)
    return "Bad Request", 400


@app.errorhandler(401)
def bad_request(error):
    error_print(401, error.description)
    return "Unauthorized", 401


@app.errorhandler(500)
def internal_error(error):
    error_print(500, error.description)
    return "Internal Error", 500


if __name__ == "__main__":
    app.run(debug=True)
