# server.py - DEBUG VERSION
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.voice_response import VoiceResponse, Say, Record
from twilio.rest import Client
import requests
import json
import traceback

app = Flask(__name__)
CORS(app)

# ============================================
# CREDENTIALS - HARDCODED
# ============================================
TWILIO_ACCOUNT_SID = "AC7157ac32a7c1840500f153d3b71f9979"
TWILIO_AUTH_TOKEN = "bf6c5e4818c8e398bbfa26266064db53"
TWILIO_PHONE_NUMBER = "+16187643399"
DEEPGRAM_API_KEY = "c50f3cfb98d6b3586fe819f36c72d8536789450f"

BASE_URL = "https://call-recording-backend.onrender.com"

print("="*60)
print("🚀 Starting Call Recorder Server (DEBUG MODE)")
print(f"📞 TWILIO_ACCOUNT_SID: {TWILIO_ACCOUNT_SID}")
print(f"📞 TWILIO_AUTH_TOKEN: {TWILIO_AUTH_TOKEN[:10]}...{TWILIO_AUTH_TOKEN[-4:]}")
print(f"📞 TWILIO_PHONE_NUMBER: {TWILIO_PHONE_NUMBER}")
print("="*60)

# ============================================
# TRY TO INITIALIZE TWILIO WITH ERROR HANDLING
# ============================================
try:
    print("🔄 Attempting to initialize Twilio client...")
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    print("✅ Twilio client created successfully!")
    
    # Test the connection
    print("🔄 Testing connection to Twilio API...")
    account = twilio_client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
    print(f"✅ Connected! Account: {account.friendly_name}")
    print(f"✅ Account Status: {account.status}")
    
except Exception as e:
    twilio_client = None
    print(f"❌ Twilio client initialization FAILED!")
    print(f"❌ Error: {e}")
    print(f"❌ Error type: {type(e).__name__}")
    print("❌ Full traceback:")
    traceback.print_exc()

transcripts = {}

@app.route('/')
def index():
    return '''
<!DOCTYPE html>
<html>
<head>
    <title>Call Recorder</title>
    <style>
        body { font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px; background: #f5f7fa; }
        h1 { color: #1a1a2e; }
        .status { padding: 10px; background: #e8f5e9; margin: 10px 0; border-radius: 5px; }
        input, button { padding: 10px; font-size: 16px; width: 100%; margin: 10px 0; }
        button { background: #1a73e8; color: white; border: none; cursor: pointer; border-radius: 5px; }
        .result { background: white; padding: 15px; border-radius: 5px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; }
        .log { background: #1a1a2e; color: #aed581; padding: 15px; border-radius: 5px; font-family: monospace; max-height: 200px; overflow-y: auto; font-size: 12px; }
        .btn-success { background: #34a853; }
        .error { background: #ffebee; color: #c62828; }
    </style>
</head>
<body>
    <h1>📞 Call Recorder</h1>
    <h3>With Deepgram Transcription</h3>
    
    <div id="status" class="status">✅ Ready</div>
    
    <h3>📱 Make a Call</h3>
    <input type="text" id="phone" placeholder="Enter phone number (e.g., +919583955784)" />
    <button onclick="makeCall()">📞 Call & Record</button>
    
    <h3>📝 Transcripts</h3>
    <div id="result" class="result">No transcripts yet</div>
    <button onclick="getTranscripts()" class="btn-success">🔄 Refresh</button>
    
    <h3>📋 Logs</h3>
    <div id="logs" class="log">⏳ Waiting...</div>

    <script>
    function addLog(msg) {
        const log = document.getElementById('logs');
        const time = new Date().toLocaleTimeString();
        log.innerHTML = time + ' ' + msg + '\\n' + log.innerHTML;
    }
    
    async function makeCall() {
        const phone = document.getElementById('phone').value;
        if (!phone) { alert('Enter a number'); return; }
        document.getElementById('status').innerHTML = '📞 Calling ' + phone + '...';
        addLog('📞 Calling ' + phone);
        try {
            const response = await fetch('/make-call', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'phone_number=' + encodeURIComponent(phone)
            });
            const data = await response.json();
            if (data.error) {
                document.getElementById('status').innerHTML = '❌ Error: ' + data.error;
                document.getElementById('status').className = 'status error';
                addLog('❌ Error: ' + data.error);
            } else {
                document.getElementById('status').innerHTML = '✅ Call initiated! Answer your phone!';
                document.getElementById('status').className = 'status';
                addLog('✅ Call SID: ' + data.call_sid);
            }
        } catch(e) {
            document.getElementById('status').innerHTML = '❌ Error';
            document.getElementById('status').className = 'status error';
            addLog('❌ ' + e.message);
        }
    }
    
    async function getTranscripts() {
        try {
            const response = await fetch('/transcripts');
            const data = await response.json();
            document.getElementById('result').innerHTML = JSON.stringify(data, null, 2);
        } catch(e) {}
    }
    
    setInterval(getTranscripts, 10000);
    getTranscripts();
    addLog('🚀 Ready! Enter a number and click Call.');
    </script>
</body>
</html>
    '''

@app.route('/voice', methods=['GET', 'POST'])
def voice():
    """Handle incoming calls - Twilio webhook"""
    print("\n📞 Incoming call received!")
    print(f"From: {request.form.get('From')}")
    print(f"To: {request.form.get('To')}")
    
    response = VoiceResponse()
    response.say("This call may be recorded for quality and training purposes.", voice="Polly.Joanna")
    response.record(
        action=BASE_URL + "/recording-callback",
        method="POST",
        max_length=3600,
        finish_on_key="",
        play_beep=False
    )
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/make-call', methods=['POST'])
def make_call():
    """Make outgoing call"""
    phone_number = request.form.get('phone_number')
    if not phone_number:
        return jsonify({"error": "Phone number required"}), 400
    
    if twilio_client is None:
        print("❌ twilio_client is None!")
        return jsonify({"error": "Twilio client not initialized. Check server logs."}), 500
    
    print(f"\n📞 Making call to: {phone_number}")
    
    response = VoiceResponse()
    response.say("This call may be recorded for quality and training purposes.", voice="Polly.Joanna")
    response.record(
        action=BASE_URL + "/recording-callback",
        method="POST",
        max_length=3600,
        finish_on_key="",
        play_beep=False
    )
    
    print(f"📝 TwiML: {response}")
    print(f"📡 Callback URL: {BASE_URL}/recording-callback")
    
    try:
        call = twilio_client.calls.create(
            twiml=str(response),
            to=phone_number,
            from_=TWILIO_PHONE_NUMBER
        )
        print(f"✅ Call SID: {call.sid}")
        return jsonify({"call_sid": call.sid})
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"❌ Error type: {type(e).__name__}")
        return jsonify({"error": str(e)}), 500

@app.route('/recording-callback', methods=['POST'])
def recording_callback():
    """Receive recording from Twilio"""
    print("\n📨 RECORDING RECEIVED!")
    data = dict(request.form)
    print(json.dumps(data, indent=2))
    
    recording_url = data.get('RecordingUrl')
    call_sid = data.get('CallSid')
    
    if recording_url and DEEPGRAM_API_KEY:
        try:
            print("🔄 Sending to Deepgram...")
            response = requests.post(
                'https://api.deepgram.com/v1/listen',
                headers={'Authorization': f'token {DEEPGRAM_API_KEY}'},
                params={'punctuate': True, 'model': 'nova-2'},
                json={"url": recording_url},
                timeout=60
            )
            if response.status_code == 200:
                result = response.json()
                transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
                transcripts[call_sid] = transcript
                print(f"📝 Transcript: {transcript}")
            else:
                print(f"❌ Deepgram error: {response.status_code}")
                print(response.text)
        except Exception as e:
            print(f"❌ Deepgram error: {e}")
    
    return "OK", 200

@app.route('/transcripts')
def get_transcripts():
    return jsonify(transcripts)

@app.route('/ping')
def ping():
    return jsonify({
        "status": "ok",
        "transcripts": len(transcripts),
        "twilio_initialized": twilio_client is not None
    })

@app.route('/debug')
def debug():
    return jsonify({
        "twilio_initialized": twilio_client is not None,
        "account_sid": TWILIO_ACCOUNT_SID[:10] + "..." if TWILIO_ACCOUNT_SID else None,
        "phone_number": TWILIO_PHONE_NUMBER,
        "has_deepgram": bool(DEEPGRAM_API_KEY),
        "base_url": BASE_URL
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
