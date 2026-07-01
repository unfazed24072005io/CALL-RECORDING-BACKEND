# server.py - Complete Rewrite for Two-Way Calling with Recording
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from twilio.twiml.voice_response import VoiceResponse, Say, Dial, Number
from twilio.rest import Client
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
import requests
import json
import traceback
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ============================================
# CREDENTIALS
# ============================================
TWILIO_ACCOUNT_SID = "AC7157ac32a7c1840500f153d3b71f9979"
TWILIO_AUTH_TOKEN = "571ef423b558b2c6cf953e01c0653835"
TWILIO_PHONE_NUMBER = "+16187643399"
DEEPGRAM_API_KEY = "c50f3cfb98d6b3586fe819f36c72d8536789450f"

# TwiML App SID - Create this in Twilio Console
# Go to: Twilio Console > Voice > TwiML Apps > Create New
# Voice URL: https://call-recording-backend.onrender.com/voice
TWIML_APP_SID = "AP2bfc7c87d94a39a39a0ecb24cc99fec8"  # REPLACE WITH YOUR TWIML APP SID

BASE_URL = "https://call-recording-backend.onrender.com"

print("="*60)
print("🚀 Starting Two-Way Call Recorder Server")
print(f"📞 TWILIO_ACCOUNT_SID: {TWILIO_ACCOUNT_SID}")
print(f"📞 TWILIO_PHONE_NUMBER: {TWILIO_PHONE_NUMBER}")
print(f"🌐 BASE_URL: {BASE_URL}")
print("="*60)

# ============================================
# INITIALIZE TWILIO CLIENT
# ============================================
try:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    account = twilio_client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
    print(f"✅ Connected! Account: {account.friendly_name}")
except Exception as e:
    twilio_client = None
    print(f"❌ Twilio client initialization FAILED: {e}")

transcripts = {}
call_logs = {}

# ============================================
# SERVE STATIC FILES
# ============================================
@app.route('/agent')
def serve_agent():
    """Serve the agent dashboard HTML"""
    return send_from_directory('.', 'agent.html')

# ============================================
# GENERATE ACCESS TOKEN FOR BROWSER SDK
# ============================================
@app.route('/token', methods=['GET', 'POST'])
def get_token():
    """Generate an Access Token for Twilio Voice JS SDK"""
    identity = request.args.get('identity', 'agent')
    
    # Create Voice Grant
    voice_grant = VoiceGrant(
        outgoing_application_sid=TWIML_APP_SID,
        incoming_allow=True
    )
    
    # Create Access Token
    token = AccessToken(
        TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN,
        identity=identity,
        ttl=3600
    )
    token.add_grant(voice_grant)
    
    return jsonify({
        'token': token.to_jwt(),
        'identity': identity
    })

# ============================================
# VOICE WEBHOOK - Twilio calls this for call handling
# ============================================
@app.route('/voice', methods=['GET', 'POST'])
def voice():
    """Handle incoming and outgoing calls - Twilio webhook"""
    print("\n📞 Voice webhook called!")
    print(f"From: {request.form.get('From')}")
    print(f"To: {request.form.get('To')}")
    
    to_number = request.form.get('To')
    from_number = request.form.get('From')
    
    response = VoiceResponse()
    
    # If this is an outbound call from the browser
    if to_number and not to_number.startswith('client:'):
        response.say("Connecting your call. This call may be recorded.", voice="Polly.Joanna")
        
        dial = Dial(
            caller_id=TWILIO_PHONE_NUMBER,
            record="record-from-answer",
            recording_track="both",
            recording_status_callback=BASE_URL + "/recording-callback",
            recording_status_callback_method="POST",
            timeout=30
        )
        dial.number(to_number)
        response.append(dial)
    
    # If this is an incoming call to your Twilio number
    else:
        response.say("This call may be recorded for quality and training purposes.", voice="Polly.Joanna")
        
        dial = Dial(
            record="record-from-answer",
            recording_track="both",
            recording_status_callback=BASE_URL + "/recording-callback",
            recording_status_callback_method="POST"
        )
        # Forward to your agent's browser client
        dial.client('agent')
        response.append(dial)
    
    print(f"📝 TwiML: {response}")
    return str(response), 200, {'Content-Type': 'text/xml'}

# ============================================
# MAKE OUTGOING CALL FROM BROWSER
# ============================================
@app.route('/call', methods=['POST'])
def make_call():
    """Initiate an outbound call from the browser"""
    data = request.get_json()
    phone_number = data.get('phone_number')
    
    if not phone_number:
        return jsonify({"error": "Phone number required"}), 400
    
    if not twilio_client:
        return jsonify({"error": "Twilio client not initialized"}), 500
    
    print(f"\n📞 Browser initiating call to: {phone_number}")
    
    # Create the TwiML response for the call
    response = VoiceResponse()
    response.say("Connecting your call. This call may be recorded.", voice="Polly.Joanna")
    
    dial = Dial(
        caller_id=TWILIO_PHONE_NUMBER,
        record="record-from-answer",
        recording_track="both",
        recording_status_callback=BASE_URL + "/recording-callback",
        recording_status_callback_method="POST",
        timeout=30
    )
    dial.number(phone_number)
    response.append(dial)
    
    # Store the TwiML for this call
    call = twilio_client.calls.create(
        twiml=str(response),
        to=phone_number,
        from_=TWILIO_PHONE_NUMBER
    )
    
    print(f"✅ Call initiated! SID: {call.sid}")
    
    return jsonify({
        "call_sid": call.sid,
        "status": "initiated",
        "message": "Call initiated successfully"
    })

# ============================================
# RECORDING CALLBACK
# ============================================
@app.route('/recording-callback', methods=['POST'])
def recording_callback():
    """Receive recording from Twilio and transcribe"""
    print("\n📨 RECORDING CALLBACK RECEIVED!")
    data = dict(request.form)
    print(json.dumps(data, indent=2))
    
    recording_url = data.get('RecordingUrl')
    call_sid = data.get('CallSid')
    recording_sid = data.get('RecordingSid')
    recording_duration = data.get('RecordingDuration')
    
    if recording_url and DEEPGRAM_API_KEY:
        try:
            print("🔄 Sending to Deepgram for transcription...")
            response = requests.post(
                'https://api.deepgram.com/v1/listen',
                headers={'Authorization': f'token {DEEPGRAM_API_KEY}'},
                params={
                    'punctuate': True,
                    'model': 'nova-2',
                    'diarize': True,
                    'dual_channel': True
                },
                json={"url": recording_url},
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                try:
                    transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
                    transcripts[call_sid or recording_sid] = {
                        'text': transcript,
                        'recording_url': recording_url,
                        'duration': recording_duration,
                        'timestamp': datetime.now().isoformat()
                    }
                    print(f"📝 Transcript: {transcript}")
                except Exception as e:
                    print(f"⚠️ Could not extract transcript: {e}")
            else:
                print(f"❌ Deepgram error: {response.status_code}")
                print(response.text)
        except Exception as e:
            print(f"❌ Deepgram error: {e}")
    
    return "OK", 200

# ============================================
# GET TRANSCRIPTS
# ============================================
@app.route('/transcripts')
def get_transcripts():
    return jsonify(transcripts)

# ============================================
# GET CALL STATUS
# ============================================
@app.route('/call-status/<call_sid>')
def get_call_status(call_sid):
    """Get the status of a call"""
    if not twilio_client:
        return jsonify({"error": "Twilio client not initialized"}), 500
    
    try:
        call = twilio_client.calls(call_sid).fetch()
        return jsonify({
            "status": call.status,
            "duration": call.duration,
            "sid": call.sid
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 404

# ============================================
# HEALTH CHECK
# ============================================
@app.route('/ping')
def ping():
    return jsonify({
        "status": "ok",
        "transcripts": len(transcripts),
        "twilio_initialized": twilio_client is not None,
        "base_url": BASE_URL
    })

@app.route('/debug')
def debug():
    return jsonify({
        "twilio_initialized": twilio_client is not None,
        "account_sid": TWILIO_ACCOUNT_SID[:10] + "..." if TWILIO_ACCOUNT_SID else None,
        "phone_number": TWILIO_PHONE_NUMBER,
        "has_deepgram": bool(DEEPGRAM_API_KEY),
        "base_url": BASE_URL,
        "twiml_app_sid": TWIML_APP_SID[:10] + "..." if TWIML_APP_SID else None
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
