from flask import Flask, render_template_string, request
import requests
import re
import uuid
from urllib.parse import urlparse, parse_qs, unquote, parse_qsl
import os

app = Flask(__name__)

# ============================================================
# 1. TOKEN EXTRACTOR LOGIC
# ============================================================
class FacebookCookieToken:
    APPS = {
        'FB_ANDROID': '350685531728',
        'MESSENGER_ANDROID': '256002347743983',
        'FB_LITE': '275254692598279',
        'MESSENGER_LITE': '200424423651082',
        'ADS_MANAGER_ANDROID': '438142079694454',
        'PAGES_MANAGER_ANDROID': '121876164619130'
    }

    USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/117.0.0.0 Safari/537.36")

    @staticmethod
    def parse_cookies(cookie_string):
        cookies = {}
        for part in cookie_string.split(';'):
            part = part.strip()
            if '=' in part:
                k, v = part.split('=', 1)
                cookies[k.strip()] = v.strip()
        return cookies

    def __init__(self, cookie_string):
        self.cookies = self.parse_cookies(cookie_string)
        if 'c_user' not in self.cookies:
            raise Exception("c_user cookie missing - invalid cookie string")
        self.cookie_header = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
        self.c_user = self.cookies['c_user']

    def _get_fb_dtsg(self):
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": self.cookie_header,
        }
        resp = requests.get(
            "https://www.facebook.com/v2.3/dialog/oauth",
            params={
                "redirect_uri": "fbconnect://success",
                "response_type": "token,code",
                "client_id": "356275264482347",
            },
            headers=headers,
            timeout=30,
        )

        if 'login' in resp.url.lower():
            raise Exception("Session expired - cookies invalid ho gayi hain. Fresh cookies nikaalein.")

        patterns = [
            r'DTSGInitialData.*?\{"token":"(.*?)"',
            r'"DTSGInitData",\[\],\{"token":"(.*?)"',
            r'name="fb_dtsg"\s+value="([^"]+)"',
            r'"fb_dtsg":"([^"]+)"',
        ]
        for pat in patterns:
            m = re.search(pat, resp.text)
            if m:
                return m.group(1)
        raise Exception("fb_dtsg nahi mila - cookies invalid ya Facebook ne structure badal diya.")

    def get_token(self):
        fb_dtsg = self._get_fb_dtsg()
        flow_uuid = str(uuid.uuid4())
        logger_uuid = str(uuid.uuid4())

        payload = (
            f"av={self.c_user}&__user={self.c_user}&fb_dtsg={fb_dtsg}"
            f"&fb_api_caller_class=RelayModern"
            f"&fb_api_req_friendly_name=useCometConsentPromptEndOfFlowBatchedMutation"
            f"&variables=%7B%22input%22%3A%7B%22client_mutation_id%22%3A%224%22%2C%22actor_id%22%3A%22{self.c_user}%22%2C%22config_enum%22%3A%22GDP_CONFIRM%22%2C%22device_id%22%3Anull%2C%22experience_id%22%3A%22{flow_uuid}%22%2C%22extra_params_json%22%3A%22%7B%5C%22app_id%5C%22%3A%5C%22350685531728%5C%22%2C%22kid_directed_site%5C%22%3A%5C%22false%5C%22%2C%22logger_id%5C%22%3A%5C%22%5C%5C%5C%22{logger_uuid}%5C%5C%5C%22%5C%22%2C%22next%5C%22%3A%5C%22%5C%5C%5C%22confirm%5C%5C%5C%22%5C%22%2C%22redirect_uri%5C%22%3A%5C%22%5C%5C%5C%22https%3A%5C%5C%5C%5C%5C%5C%2F%5C%5C%5C%5C%5C%2Fwww.facebook.com%5C%5C%5C%5C%5C%5C%2Fconnect%5C%5C%5C%5C%5C%5C%2Flogin_success.html%5C%5C%5C%22%5C%22%2C%22response_type%5C%22%3A%5C%22%5C%5C%5C%22token%5C%5C%5C%22%5C%22%2C%22return_scopes%5C%22%3A%5C%22false%5C%22%2C%22scope%5C%22%3A%5C%22%5B%5C%5C%5C%22user_subscriptions%5C%5C%5C%22%5D%5C%22%7D%22%2C%22flow_name%22%3A%22GDP%22%2C%22flow_step_type%22%3A%22STANDALONE%22%2C%22outcome%22%3A%22APPROVED%22%2C%22source%22%3A%22gdp_delegated%22%2C%22surface%22%3A%22FACEBOOK_COMET%22%7D%7D"
            f"&server_timestamps=true&doc_id=6494107973937368"
        )

        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.facebook.com",
            "user-agent": self.USER_AGENT,
            "x-fb-friendly-name": "useCometConsentPromptEndOfFlowBatchedMutation",
            "cookie": self.cookie_header,
        }

        resp = requests.post(
            "https://www.facebook.com/api/graphql/",
            data=payload,
            headers=headers,
            timeout=30,
        )

        try:
            data = resp.json()
        except ValueError:
            raise Exception(f"GraphQL response JSON nahi hai: {resp.text[:200]}")

        uri = data.get("data", {}).get("run_post_flow_action", {}).get("uri")
        if not uri:
            raise Exception("access_token nahi mila - doc_id outdated ho sakta hai.")

        parsed = urlparse(uri)
        q = parse_qs(parsed.query)
        close_uri = unquote(q.get("close_uri", [""])[0])
        frag = urlparse(close_uri).fragment
        frag_params = dict(parse_qsl(frag)) if frag else {}

        access_token = frag_params.get("access_token")
        if not access_token:
            raise Exception("Fragment mein access_token nahi mila")

        return access_token

    def convert_token(self, access_token, target_app):
        try:
            app_id = self.APPS.get(target_app)
            if not app_id:
                return None

            r = requests.post(
                'https://api.facebook.com/method/auth.getSessionforApp',
                data={
                    'access_token': access_token,
                    'format': 'json',
                    'new_app_id': app_id,
                    'generate_session_cookies': '1'
                },
                timeout=30
            )
            res = r.json()

            if 'access_token' not in res:
                return None
            return res['access_token']
        except Exception:
            return None

# ============================================================
# 2. EMBEDDED HTML UI (Ek hi file mein)
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FB Token Extractor</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; padding: 20px; color: #333; }
        .container { max-width: 800px; margin: auto; background: white; padding: 25px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        h1 { color: #1877f2; text-align: center; margin-bottom: 20px; }
        textarea { width: 100%; height: 120px; padding: 12px; border: 1px solid #ccc; border-radius: 6px; font-family: monospace; resize: vertical; box-sizing: border-box; }
        button { background: #1877f2; color: white; border: none; padding: 12px; border-radius: 6px; cursor: pointer; font-size: 16px; width: 100%; margin-top: 15px; font-weight: bold; transition: 0.3s; }
        button:hover { background: #166fe5; }
        .error { background: #ffebe8; color: #cc0000; padding: 12px; border-radius: 6px; margin-bottom: 15px; border: 1px solid #ffcccc; }
        .result { margin-top: 25px; }
        .token-box { background: #e8f5e9; padding: 15px; border-radius: 6px; border: 1px solid #c8e6c9; margin-bottom: 15px; }
        .token { font-family: monospace; word-break: break-all; font-weight: bold; color: #2e7d32; font-size: 15px; }
        .app-token { background: #f8f9fa; padding: 12px; border: 1px solid #ddd; margin-bottom: 8px; border-radius: 6px; font-family: monospace; word-break: break-all; font-size: 13px; }
        .label { font-weight: bold; margin-bottom: 8px; display: block; color: #555; }
        .success-title { color: #2e7d32; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🍪 FB Cookie → Access Token</h1>

        {% if error %}
            <div class="error"><strong>❌ Error:</strong> {{ error }}</div>
        {% endif %}

        <form method="POST">
            <label class="label">Facebook Cookies paste karein (c_user=...; xs=...; datr=...):</label>
            <textarea name="cookies" placeholder="datr=...; sb=...; c_user=...; xs=...">{{ cookies }}</textarea>
            <button type="submit">Get Tokens 🚀</button>
        </form>

        {% if token %}
            <div class="result">
                <h2 class="success-title">✅ Success! Token Mil Gaya</h2>
                
                <div class="token-box">
                    <span class="label">Original Access Token:</span>
                    <div class="token">{{ token }}</div>
                </div>

                {% if converted %}
                    <span class="label">Converted Tokens:</span>
                    {% for app, app_token in converted.items() %}
                        <div class="app-token">
                            <strong style="color:#1877f2;">[{{ app }}]</strong><br>
                            {{ app_token }}
                        </div>
                    {% endfor %}
                {% endif %}
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

# ============================================================
# 3. FLASK ROUTES
# ============================================================
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        cookie_string = request.form.get('cookies', '').strip()
        
        if not cookie_string:
            return render_template_string(HTML_TEMPLATE, error="Cookies daalna zaroori hai!")

        try:
            fb = FacebookCookieToken(cookie_string)
            token = fb.get_token()
            
            converted = {}
            for app_key in fb.APPS:
                res = fb.convert_token(token, app_key)
                if res:
                    converted[app_key] = res

            return render_template_string(HTML_TEMPLATE, 
                                          token=token, 
                                          converted=converted, 
                                          cookies=cookie_string)
        
        except Exception as e:
            return render_template_string(HTML_TEMPLATE, error=str(e), cookies=cookie_string)

    return render_template_string(HTML_TEMPLATE)

# ============================================================
# 4. RUN APP
# ============================================================
if __name__ == '__main__':
    # Railway ya localhost dono ke liye port handle karega
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
