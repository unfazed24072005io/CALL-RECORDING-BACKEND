# server.py - FIXED: No second dial!
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.voice_response import VoiceResponse, Say, Record
from twilio.rest import Client
import requests
import json

app = Flask(__name__)
CORS(app)

# YOUR CREDENTIALS
TWILIO_ACCOUNT_SID = "AC7157ac32a7c1840500f153d3b71f9979"
TWILIO_AUTH_TOKEN = "c2e7a8036607d884cdd82c8beecfe3c0"
TWILIO_PHONE_NUMBER = "+16187643399"
DEEPGRAM_API_KEY = "c50f3cfb98d6b3586fe819f36c72d8536789450f"
NGROK_URL = "https://nondefined-ungrayed-cayla.ngrok-free.dev"

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
transcripts = {}

@app.route('/')
def index():
    return '''
<!DOCTYPE html>
<html>
<head>
    <title>Call Recorder</title>
    <style>
        body { font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px; }
        input, button { padding: 10px; font-size: 16px; width: 100%; margin: 10px 0; }
        button { background: #1a73e8; color: white; border: none; cursor: pointer; border-radius: 5px; }
        .result { background: #f5f5f5; padding: 15px; border-radius: 5px; margin-top: 20px; }
        .status { padding: 10px; background: #e8f5e9; margin: 10px 0; border-radius: 5px; }
        .log { background: #1a1a2e; color: #aed581; padding: 15px; border-radius: 5px; font-family: monospace; max-height: 200px; overflow-y: auto; font-size: 12px; }
    </style>
</head>
<body>
    <h1>📞 Call Recorder</h1>
    <p>Enter a number to call</p>
    
    <div id="status" class="status">✅ Ready</div>
    
    <input type="text" id="phone" placeholder="Enter number (e.g., +919583955784)" />
    <button onclick="makeCall()">📞 Call & Record</button>
    
    <h3>📝 Transcripts</h3>
    <div id="result" class="result">No transcripts yet</div>
    <button onclick="getTranscripts()" style="background:#34a853;">🔄 Refresh</button>
    
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
                addLog('❌ Error: ' + data.error);
            } else {
                document.getElementById('status').innerHTML = '✅ Call initiated! Answer your phone!';
                addLog('✅ Call SID: ' + data.call_sid);
            }
        } catch(e) {
            document.getElementById('status').innerHTML = '❌ Error';
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

@app.route('/make-call', methods=['POST'])
def make_call():
    """Make outgoing call - ONE CALL, NO SECOND DIAL"""
    phone_number = request.form.get('phone_number')
    if not phone_number:
        return jsonify({"error": "Phone number required"}), 400
    
    print(f"\n📞 Making call to: {phone_number}")
    
    # IMPORTANT: The caller is the person who will receive the call
    # We don't need to dial again because Twilio calls them directly
    
    # Create TwiML that will be executed on the call
    response = VoiceResponse()
    
    # Play the message
    response.say("This call may be recorded for quality and training purposes.", voice="Polly.Joanna")
    
    # CRITICAL FIX: Record the call - NO DIAL!
    # The call is already connected to the number we're calling
    response.record(
        action=NGROK_URL + "/recording-callback",
        method="POST",
        max_length=3600,
        finish_on_key="",
        play_beep=False
    )
    
    print(f"📝 TwiML: {response}")
    
    try:
        # Twilio calls the number directly with the TwiML instructions
        call = twilio_client.calls.create(
            twiml=str(response),
            to=phone_number,
            from_=TWILIO_PHONE_NUMBER
        )
        print(f"✅ Call SID: {call.sid}")
        return jsonify({"call_sid": call.sid})
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/recording-callback', methods=['POST'])
def recording_callback():
    """Receive recording from Twilio"""
    print("\n📨 RECORDING RECEIVED!")
    data = dict(request.form)
    print(json.dumps(data, indent=2))
    
    recording_url = data.get('RecordingUrl')
    call_sid = data.get('CallSid')
    
    if recording_url:
        try:
            response = requests.post(
                'https://api.deepgram.com/v1/listen',
                headers={'Authorization': f'token {DEEPGRAM_API_KEY}'},
                params={'punctuate': True, 'model': 'nova-2'},
                json={"url": recording_url}
            )
            if response.status_code == 200:
                result = response.json()
                transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
                transcripts[call_sid] = transcript
                print(f"📝 Transcript: {transcript}")
        except Exception as e:
            print(f"Deepgram error: {e}")
    
    return "OK", 200

@app.route('/transcripts')
def get_transcripts():
    return jsonify(transcripts)

@app.route('/ping')
def ping():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 Starting Call Recorder")
    print(f"📞 Twilio: {TWILIO_PHONE_NUMBER}")
    print(f"🌐 ngrok: {NGROK_URL}")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)