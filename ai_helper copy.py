import os
import time
import random
import json
import subprocess
import re
import requests
from datetime import datetime
from functools import wraps
import threading

# === Global API & Model Health Tracker (v110.2) === #
class APIHealth:
    def __init__(self):
        self.lock = threading.RLock() # 🏛️ [VANTIX STABILITY]: Re-entrant lock to prevent recursive deadlocks
        self.provider_priority = ["groq", "openrouter"]
        self.model_priority = {
            "groq": [
                "llama-3.3-70b-versatile",
                "llama-3.1-8b-instant"
            ],
            "openrouter": [
                "google/gemini-2.0-flash-001",
                "google/gemini-2.0-flash-lite-001",
                "meta-llama/llama-3.3-70b-instruct", 
                "qwen/qwen-2.5-72b-instruct"
            ],
            "image": [
                "google/gemini-2.0-flash-001",
                "stabilityai/sdxl",
                "openai/dall-e-3"
            ]
        }
        self.cooldowns = {} # {provider:model: timestamp}

    def report_success(self, provider, model=None):
        with self.lock:
            key = f"{provider}:{model}" if model else provider
            if key in self.cooldowns: del self.cooldowns[key]
            
            if provider in self.provider_priority:
                self.provider_priority.remove(provider)
                self.provider_priority.insert(0, provider)

    def report_failure(self, provider, model=None):
        with self.lock:
            key = f"{provider}:{model}" if model else provider
            # 🛡️ [VANTIX STABILIZATION]: Increased to 60s to absolute-mitigate 429 bursts (v124.50)
            self.cooldowns[key] = time.time() + 60 
            
            if not model and provider in self.provider_priority:
                self.provider_priority.remove(provider)
                self.provider_priority.append(provider)
                
            if model and provider in self.model_priority:
                models = self.model_priority[provider]
                if model in models:
                    models.remove(model)
                    models.append(model)
            print(f"📉 [HEALTH] {provider.upper()}{':' + model if model else ''} cooled-down (60s buffer).")

    def is_healthy(self, provider, model=None):
        with self.lock:
            key = f"{provider}:{model}" if model else provider
            if key in self.cooldowns:
                if time.time() > self.cooldowns[key]:
                    del self.cooldowns[key]
                    return True
                return False
            return True

    def get_providers(self):
        with self.lock:
            return [p for p in self.provider_priority if self.is_healthy(p)]

    def get_models(self, provider):
        with self.lock:
            return [m for m in self.model_priority.get(provider, []) if self.is_healthy(provider, m)]

HEALTH_TRACKER = APIHealth()

# === Response Class === #
class AIResponse:
    def __init__(self, text):
        self.text = text

# === Groq Backend === #
def call_groq(prompt, user_keys=None):
    api_key = (user_keys or {}).get("groq") or os.environ.get("GROQ_API_KEY")
    if not api_key: raise ValueError("Groq API Key missing.")
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    models = HEALTH_TRACKER.get_models("groq")
    for model in models:
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
        try:
            print(f"📡 Groq Requesting {model}...")
            response = requests.post(url, headers=headers, json=payload, timeout=25)
            if response.status_code == 200:
                HEALTH_TRACKER.report_success("groq", model)
                print(f"✅ Groq ({model}) success.")
                return AIResponse(response.json()["choices"][0]["message"]["content"].strip())
            else:
                print(f"⚠️ Groq Error {response.status_code}: {response.text[:150]}")
                # If rate limit, cooldown the model
                if response.status_code == 429:
                    HEALTH_TRACKER.report_failure("groq", model)
        except Exception as e:
            print(f"❌ Groq Exception: {e}")
            HEALTH_TRACKER.report_failure("groq", model)
            
    raise RuntimeError("All Groq models failed.")

# === OpenRouter Backend === #
def call_openrouter(prompt, user_keys=None):
    api_key = (user_keys or {}).get("openrouter") or os.environ.get("OPENROUTER_API_KEY")
    if not api_key: raise ValueError("OpenRouter API Key missing.")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/udaydomadiya08/VIDEOYT",
        "X-Title": "Vantix Video Platform"
    }
    
    models = HEALTH_TRACKER.get_models("openrouter")
    for model in models:
        payload = {
            "model": model, 
            "messages": [{"role": "user", "content": prompt}], 
            "temperature": 0.7,
            "max_tokens": 2048
        }
        
        def attempt_request(current_payload):
            try:
                print(f"📡 Requesting {model}...")
                response = requests.post(url, headers=headers, json=current_payload, timeout=70)
                if response.status_code == 200:
                    HEALTH_TRACKER.report_success("openrouter", model)
                    print(f"✅ OpenRouter ({model}) success.")
                    return AIResponse(response.json()["choices"][0]["message"]["content"].strip())
                
                # 🛡️ [ADAPTIVE TOKEN SCALING]: Credit-Sensing Fallback (v124.44)
                if response.status_code == 402:
                    error_msg = response.text
                    print(f"⚠️ [CREDIT ALERT] OpenRouter 402: {error_msg[:100]}")
                    
                    # 🚫 [ZERO BALANCE]: Skip scale-down if account is empty (v124.45)
                    if "Insufficient credits" in error_msg:
                        print("📉 [CREDIT] Zero balance detected. Skipping scale-down retry.")
                        HEALTH_TRACKER.report_failure("openrouter", model)
                        return None

                    match = re.search(r"only afford (\d+)", error_msg)
                    if match:
                        afforded = int(match.group(1))
                        # Retry ONCE with the afforded limit - 50 buffer
                        retry_tokens = max(150, afforded - 50)
                        print(f"📉 [ADAPTIVE] Scaling down to {retry_tokens} tokens to certify authorization...")
                        current_payload["max_tokens"] = retry_tokens
                        # Recursive single retry
                        retry_resp = requests.post(url, headers=headers, json=current_payload, timeout=70)
                        if retry_resp.status_code == 200:
                            HEALTH_TRACKER.report_success("openrouter", model)
                            print(f"✅ [ADAPTIVE SUCCESS] Scale-down authorized.")
                            return AIResponse(retry_resp.json()["choices"][0]["message"]["content"].strip())
                    
                    HEALTH_TRACKER.report_failure("openrouter", model)
                elif response.status_code == 429:
                    HEALTH_TRACKER.report_failure("openrouter", model)
                elif response.status_code == 401: 
                    print("🚫 [SECURITY] OpenRouter API Key INVALID/EXPIRED.")
                    return "SKIP_KEY"
                else:
                    print(f"⚠️ [API ERROR] OpenRouter {response.status_code}: {response.text[:150]}")
            except Exception as e:
                print(f"❌ [EXCEPTION] OpenRouter: {e}")
                HEALTH_TRACKER.report_failure("openrouter", model)
            return None

        res = attempt_request(payload)
        if res == "SKIP_KEY": break
        if res: return res
            
    raise RuntimeError("OpenRouter Cycle Exhausted.")

# === Main Synthesis Entry === #
def generate_ai_response(prompt, user_keys=None, job_id=None):
    if os.environ.get("TURBO_MODE", "false").lower() == "true":
        print("🚀 [VANTIX TURBO]: Universal Thinking Bypass Active.")
        return AIResponse("Verification synthesis active. Industrial bridge confirmed.")
        
    import api.telemetry as telemetry
    retry_count = 0
    
    while retry_count < 2:
        providers = HEALTH_TRACKER.get_providers()
        if not providers:
            print("🚨 [CRITICAL] No healthy providers found. Waiting for industrial recovery...")
        
        for provider in providers:
            try:
                if job_id: telemetry.update_progress(job_id, f"AI {provider.upper()} Thinking...")
                if provider == "groq": return call_groq(prompt, user_keys=user_keys)
                if provider == "openrouter": return call_openrouter(prompt, user_keys=user_keys)
            except Exception as e:
                print(f"🔄 [FAILOVER] {provider.upper()} exhausted. Switching provider... (Error: {e})")
                continue # Immediate switch to next provider in SAME retry cycle
        
        # 📈 [SOVEREIGN DELAY] Triggered ONLY if ALL providers fail in a single sweep
        retry_count += 1
        sleep_time = 15
        msg = f"AI Retrying ({retry_count}/2)..."
        if job_id: telemetry.update_progress(job_id, msg)
        print(f"🚨 Global API Exhaustion ({retry_count}/2). Pausing {sleep_time}s...")
        time.sleep(sleep_time)
    
    raise RuntimeError("Critical: Permanent AI Infrastructure failure.")

# === Image & Other Helpers === #
def generate_image_asset(prompt, user_keys=None):
    api_key = (user_keys or {}).get("openrouter") or os.environ.get("OPENROUTER_API_KEY")
    if not api_key: return None
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for model in HEALTH_TRACKER.get_models("image"):
        try:
            response = requests.post(url, headers=headers, json={"model": model, "prompt": prompt}, timeout=40)
            if response.status_code == 200:
                data = response.json()
                url = data.get("url") or data.get("choices",[{}])[0].get("message",{}).get("content")
                if url and url.startswith("http"): return url
        except: pass
    return None

def generate_ebook_theme(topic, description="", user_keys=None):
    prompt = f"Design visual DNA for '{topic}'. Vision: {description}. Return ONLY JSON: primary_rgb, secondary_rgb, layout_mode, visual_style."
    try:
        response = generate_ai_response(prompt, user_keys=user_keys)
        match = re.search(r"\{.*\}", response.text, re.DOTALL)
        if match: return json.loads(match.group(0))
    except: pass
    return {
        "primary_rgb": [20, 20, 20], 
        "secondary_rgb": [200, 0, 0], 
        "layout_mode": "Sophisticated",
        "visual_style": "Cinematic"
    }
