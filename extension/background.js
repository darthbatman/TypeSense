/* Globals */


// For calling GET and SET to the extension's local storage
const storage = chrome.storage.local;

/*
// Creates an HTTP POST request
const post = (url, payload, callback) => {
	let xhr = new XMLHttpRequest();
	xhr.open("POST", url, true);
	xhr.setRequestHeader("Content-type", "application/json");
	xhr.onreadystatechange = () => {
		if (xhr.readyState == XMLHttpRequest.DONE && xhr.status == 200) // readyState == 4
			callback(xhr.responseText);
	}
	xhr.send(JSON.stringify(payload));
}
*/

// Sends a message to content scripts running in the current tab
const message = (content) => {
	chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
		let activeTab = tabs[0];
		chrome.tabs.sendMessage(activeTab.id, content);
	});
}

// Transforms a Messages object into a SentimentTable object
const analyzeSentiment = (messages) => {
	// TODO: Require VADER-js
	// TODO: Output ordered list of dictionaries, formatted as [{"message": "...", "received": "...", "sentiment": 0}, ...]
	return [
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": false, "sentiment": -.50},
		{"message": "", "received": false, "sentiment": -.50},
		{"message": "", "received": false, "sentiment": -.50},
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": false, "sentiment": -.50},
		{"message": "", "received": false, "sentiment": -.50},
		{"message": "", "received": false, "sentiment": -.50},
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": true, "sentiment": .25},
		{"message": "", "received": false, "sentiment": -.50},
		{"message": "", "received": false, "sentiment": -.40}
	] // TEMP
}


/* Event Listeners */


// Listens for messenger.com to be loaded and sends "inject-listeners" to listeners.js
chrome.webNavigation.onCompleted.addListener((details) => {
	if (details.url.includes("messenger.com")) {
		message({"message": "injectListeners"}); // Tells listeners.js to inject event listeners
	}
});

/*
// Listens for when the extension is first installed or updated
chrome.runtime.onInstalled.addListener((details) => {
	if (details.reason == "install") {
		console.log("User has installed TypeSense for the first time on this device.");
	} else if (details.reason == "update") {
		let thisVersion = chrome.runtime.getManifest().version;
		console.log("Updated from " + details.previousVersion + " to " + thisVersion + " :)");
	}
});
*/

// Listens for long-lived port connections (from content scripts)
chrome.runtime.onConnect.addListener((port) => {
	port.onMessage.addListener((msg) => {
		if (port.name == "listener") { // Handles requests from listeners.js
			let sentimentTable = analyzeSentiment(msg.messages);

			storage.set({"currentThread": sentimentTable}, () => { // TODO: Memoize conversations
				console.log("Populated conversation's sentiment table.");
			});

			// Updates the browser action icon according to sentiment change
			if (sentimentTable[sentimentTable.length - 1]["sentiment"] >= sentimentTable[sentimentTable.length - 2]["sentiment"]) // Sentiment increased
				chrome.browserAction.setIcon({path: "../assets/icon_green.png"});
			else // Sentiment decreased
				chrome.browserAction.setIcon({path: "../assets/icon_red.png"});
		}
	});
});
