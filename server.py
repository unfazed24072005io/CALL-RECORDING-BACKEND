# server.py - Complete Two-Way Call Recorder
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from twilio.twiml.voice_response import VoiceResponse, Say, Dial
from twilio.rest import Client
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
import requests
import json
import traceback
from datetime import datetime

# ============================================
# FIREBASE ADMIN SDK - RENDER COMPATIBLE
# ============================================
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    import json as json_module
    
    # Try environment variable first (for Render)
    firebase_creds = os.getenv('FIREBASE_SERVICE_ACCOUNT')
    if firebase_creds:
        try:
            cred_dict = json_module.loads(firebase_creds)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("✅ Firebase connected via environment variable!")
        except Exception as e:
            db = None
            print(f"❌ Firebase env var error: {e}")
    # Fallback to local file (for local development)
    elif os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase connected via local file!")
    else:
        db = None
        print("⚠️ No Firebase credentials found - recordings NOT saved")
        print("   Set FIREBASE_SERVICE_ACCOUNT env var or add serviceAccountKey.json")
except ImportError:
    db = None
    print("⚠️ firebase-admin not installed - recordings NOT saved")
    print("   Install with: pip install firebase-admin")
except Exception as e:
    db = None
    print(f"⚠️ Firebase error: {e}")

app = Flask(__name__)
CORS(app)

# ============================================
# CREDENTIALS - REPLACE WITH YOURS
# ============================================
TWILIO_ACCOUNT_SID = "AC7157ac32a7c1840500f153d3b71f9979"
TWILIO_AUTH_TOKEN = "dfd6a9f24bd5abd9607fdf7336d9b82f"

# Create API Key in Twilio Console: Settings > API Keys & Tokens
TWILIO_API_KEY_SID = "SK184c8eee37a3f35fed669225cd7e1a0c"
TWILIO_API_KEY_SECRET = "hjzaqwzS6jqoY5NtZWK6SCoDIaQQn6LD"

TWILIO_PHONE_NUMBER = "+16187643399"
DEEPGRAM_API_KEY = "c50f3cfb98d6b3586fe819f36c72d8536789450f"

# Create TwiML App in Twilio Console: Voice > TwiML Apps
TWIML_APP_SID = "AP2bfc7c87d94a39a39a0ecb24cc99fec8"

# ============================================
# BASE_URL - AUTO DETECT FOR RENDER
# ============================================
if os.environ.get('RENDER'):
    BASE_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://call-recording-backend.onrender.com')
else:
    BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')

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

# ============================================
# SERVE STATIC FILES
# ============================================
@app.route('/')
def index():
    """Serve the main page"""
    return send_from_directory('.', 'agent.html')

@app.route('/agent')
def serve_agent():
    """Serve the agent dashboard"""
    return send_from_directory('.', 'agent.html')

@app.route('/node_modules/<path:filename>')
def serve_node_modules(filename):
    """Serve node_modules for Twilio SDK"""
    return send_from_directory('node_modules', filename)

# ✅ ADD THIS ROUTE
@app.route('/twilio.min.js')
def serve_twilio_sdk():
    """Serve the local Twilio SDK file"""
    return send_from_directory('.', 'twilio.min.js')

# ============================================
# GENERATE ACCESS TOKEN FOR BROWSER SDK
# ============================================
@app.route('/token', methods=['GET', 'POST'])
def get_token():
    """Generate an Access Token for Twilio Voice JS SDK"""
    try:
        identity = request.args.get('identity', 'agent')
        
        # Create Voice Grant
        voice_grant = VoiceGrant(
            outgoing_application_sid=TWIML_APP_SID,
            incoming_allow=True
        )
        
        # Create Access Token with API Key
        token = AccessToken(
            TWILIO_ACCOUNT_SID,
            TWILIO_API_KEY_SID,
            TWILIO_API_KEY_SECRET,
            identity=identity,
            ttl=3600
        )
        token.add_grant(voice_grant)
        
        return jsonify({
            'token': token.to_jwt(),
            'identity': identity
        })
    except Exception as e:
        print(f"❌ Token generation error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

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
# GET RECORDING URL FROM TWILIO - NEW ENDPOINT
# ============================================
@app.route('/recording/<recording_sid>', methods=['GET'])
def get_recording(recording_sid):
    """Get recording URL from Twilio"""
    try:
        if not twilio_client:
            return jsonify({"error": "Twilio client not initialized"}), 500
        
        # Fetch recording from Twilio
        recording = twilio_client.recordings(recording_sid).fetch()
        
        # Generate the recording URL
        recording_url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Recordings/{recording_sid}.mp3"
        
        return jsonify({
            "recording_sid": recording_sid,
            "recording_url": recording_url,
            "status": recording.status,
            "duration": recording.duration,
            "call_sid": recording.call_sid
        })
    except Exception as e:
        print(f"❌ Error fetching recording: {e}")
        return jsonify({"error": str(e)}), 404

# ============================================
# RECORDING CALLBACK - UPDATED WITH FIXES
# ============================================
@app.route('/recording-callback', methods=['POST'])
def recording_callback():
    """Receive recording from Twilio, save to Firebase, and transcribe"""
    print("\n📨 RECORDING CALLBACK RECEIVED!")
    data = dict(request.form)
    print(json.dumps(data, indent=2))
    
    recording_url = data.get('RecordingUrl')
    call_sid = data.get('CallSid')
    recording_sid = data.get('RecordingSid')
    recording_duration = data.get('RecordingDuration')
    
    # ===== SAVE RECORDING SID TO FIREBASE (with create if not exists) =====
    if call_sid and recording_sid and db is not None:
        try:
            doc_ref = db.collection('calls').document(call_sid)
            doc = doc_ref.get()
            
            if doc.exists:
                doc_ref.update({
                    'recordingSid': recording_sid,
                    'recordingUrl': recording_url,
                    'recordingDuration': int(recording_duration) if recording_duration else None,
                    'hasRecording': True,
                    'updatedAt': firestore.SERVER_TIMESTAMP
                })
                print(f"✅ Updated recording SID {recording_sid} for call {call_sid}")
            else:
                doc_ref.set({
                    'callSid': call_sid,
                    'recordingSid': recording_sid,
                    'recordingUrl': recording_url,
                    'recordingDuration': int(recording_duration) if recording_duration else None,
                    'hasRecording': True,
                    'createdAt': firestore.SERVER_TIMESTAMP,
                    'updatedAt': firestore.SERVER_TIMESTAMP
                })
                print(f"✅ Created new call document with recording SID {recording_sid}")
        except Exception as e:
            print(f"❌ Failed to save recording to Firebase: {e}")
    elif call_sid and recording_sid:
        print(f"⚠️ Firebase not available - recording SID {recording_sid} not saved")
    
    # ===== TRANSCRIPTION - UPDATED DEEPGRAM PARAMS =====
    if recording_url and DEEPGRAM_API_KEY:
        try:
            print("🔄 Sending to Deepgram for transcription...")
            response = requests.post(
                'https://api.deepgram.com/v1/listen',
                headers={'Authorization': f'token {DEEPGRAM_API_KEY}'},
                params={
                    'punctuate': 'true',
                    'model': 'nova-2',
                    'diarize': 'true',
                    'dual_channel': 'true'
                },
                json={"url": recording_url},
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                try:
                    transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
                    
                    # ===== SAVE TRANSCRIPT TO FIREBASE =====
                    if call_sid and transcript and db is not None:
                        try:
                            doc_ref = db.collection('calls').document(call_sid)
                            doc_ref.update({
                                'transcript': transcript,
                                'hasTranscript': True,
                                'transcriptUpdatedAt': firestore.SERVER_TIMESTAMP
                            })
                            print(f"📝 Saved transcript for call {call_sid} to Firebase")
                        except Exception as e:
                            print(f"⚠️ Failed to save transcript to Firebase: {e}")
                    
                    # Keep existing in-memory storage (unchanged)
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
# GET TRANSCRIPTS - UNCHANGED
# ============================================
@app.route('/transcripts')
def get_transcripts():
    return jsonify(transcripts)

# ============================================
# GET CALL STATUS - UNCHANGED
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
# HEALTH CHECK - UNCHANGED
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
        "twiml_app_sid": TWIML_APP_SID[:10] + "..." if TWIML_APP_SID else None,
        "api_key_configured": bool(TWILIO_API_KEY_SID and TWILIO_API_KEY_SID != "SKxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"),
        "firebase_initialized": db is not None
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
