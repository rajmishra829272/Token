import requests
import re
import uuid
import os
import sys
from urllib.parse import urlparse, parse_qs, unquote, parse_qsl

# ============================================================
# FACEBOOK COOKIE → ACCESS TOKEN EXTRACTOR
# ============================================================

class FacebookCookieToken:

    # App IDs for token conversion
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
        """OAuth dialog page se fb_dtsg token nikalta hai"""
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
            raise Exception("Session expired - cookies invalid ho gayi hain.")

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
        raise Exception("fb_dtsg nahi mila - cookies invalid ya Facebook ne structure badal diya")

    def get_token(self):
        """Main method - access_token return karta hai"""
        print("[*] fb_dtsg fetch ho raha hai...")
        fb_dtsg = self._get_fb_dtsg()
        print(f"[+] fb_dtsg: {fb_dtsg[:20]}...")

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

        print("[*] GraphQL request bhej rahe hain...")
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
            raise Exception(
                f"access_token nahi mila - doc_id outdated ho sakta hai. "
                f"Response: {str(data)[:300]}"
            )

        parsed = urlparse(uri)
        q = parse_qs(parsed.query)
        close_uri = unquote(q.get("close_uri", [""])[0])
        frag = urlparse(close_uri).fragment
        frag_params = dict(parse_qsl(frag)) if frag else {}

        access_token = frag_params.get("access_token")
        if not access_token:
            raise Exception(f"Fragment mein access_token nahi mila")

        return access_token

    def convert_token(self, access_token, target_app):
        """Original token ko kisi doosre app ke token mein convert karta hai"""
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

            token = res['access_token']
            cookies_str = ""
            if 'session_cookies' in res:
                cookies_str = "; ".join(
                    f"{c['name']}={c['value']}" for c in res['session_cookies']
                )
            return {'token': token, 'cookies': cookies_str}
        except Exception:
            return None


# ============================================================
# MAIN EXECUTION (Railway / Non-Interactive Safe)
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  Facebook Cookie → Access Token (Railway Edition)")
    print("=" * 60)

    # Railway Environment Variable se cookies uthao
    cookie_string = os.environ.get("FB_COOKIES", "").strip()

    # Fallback: Agar locally chala rahe ho toh input le lo
    if not cookie_string:
        try:
            cookie_string = input("\nCookies paste karein:\n> ").strip()
        except EOFError:
            pass

    if not cookie_string:
        print("\n[!] Cookie nahi mili.")
        print("[!] Railway ke 'Variables' tab mein 'FB_COOKIES' variable set karein.")
        sys.exit(1)

    try:
        fb = FacebookCookieToken(cookie_string)
        print(f"\n[+] c_user: {fb.c_user}")

        token = fb.get_token()

        print("\n" + "=" * 60)
        print("SUCCESS - ACCESS TOKEN MILA")
        print("=" * 60)
        print(f"\nOriginal Token:\n{token}\n")

        # Convert to other apps
        print("=" * 60)
        print("CONVERTED TOKENS")
        print("=" * 60)
        for app_key in fb.APPS:
            result = fb.convert_token(token, app_key)
            if result:
                print(f"\n[{app_key}]")
                print(f"Token: {result['token']}")
                if result['cookies']:
                    print(f"Cookies: {result['cookies']}")
            else:
                print(f"\n[{app_key}] ❌ conversion failed")

    except Exception as e:
        print("\n" + "=" * 60)
        print("ERROR")
        print("=" * 60)
        print(f"{e}")
        sys.exit(1)
