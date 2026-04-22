import os
import time
import json
import re
import asyncio
import httpx
from datetime import datetime

# === Global API & Model Health Tracker === #
class APIHealth:
    def __init__(self):
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
            ]
        }
        self.cooldowns = {}

    def report_success(self, provider, model=None):
        key = f"{provider}:{model}" if model else provider
        if key in self.cooldowns: del self.cooldowns[key]

    def report_failure(self, provider, model=None):
        key = f"{provider}:{model}" if model else provider
        self.cooldowns[key] = time.time() + 60 
        print(f"📉 [HEALTH] {provider.upper()}{':' + model if model else ''} cooled-down.")

    def is_healthy(self, provider, model=None):
        key = f"{provider}:{model}" if model else provider
        if key in self.cooldowns:
            if time.time() > self.cooldowns[key]:
                del self.cooldowns[key]
                return True
            return False
        return True

    def get_providers(self):
        return [p for p in self.provider_priority if self.is_healthy(p)]

    def get_models(self, provider):
        return [m for m in self.model_priority.get(provider, []) if self.is_healthy(provider, m)]

HEALTH_TRACKER = APIHealth()

# === Helper: Shared Internet Check (Import safe) === #
async def wait_for_internet_helper():
    """Wait until internet is restored using a simple fast check."""
    import socket
    while True:
        try:
            socket.setdefaulttimeout(1)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            return True
        except:
            await asyncio.sleep(2)

# === AI Response Classes === #
class AIResponse:
    def __init__(self, text):
        self.text = text

# === Main Synthesis Entry === #
async def generate_ai_response_stream(prompt, user_keys=None, raw_query=None, force_normal=False):
    """Yields chunks of text from the best available AI model (ASYNC)."""
    api_key = (user_keys or {}).get("groq") or os.environ.get("GROQ_API_KEY")
    or_key = (user_keys or {}).get("openrouter") or os.environ.get("OPENROUTER_API_KEY")
    
    max_retries = 3
    
    for attempt in range(max_retries):
        # === PATH 1: HIGH-SPEED GROQ ===
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "stream": True
            }
            
            print(f"📡 [GROQ-STREAM] Processing (Attempt {attempt+1})...")
            req_start = time.time()
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, read=20.0)) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code == 200:
                        first_token = True
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                                if data_str == "[DONE]": break
                                try:
                                    chunk = json.loads(data_str)
                                    content = chunk["choices"][0]["delta"].get("content", "")
                                    if content:
                                        if first_token:
                                            print(f"🚀 [GROQ] First token in {time.time() - req_start:.2f}s")
                                            first_token = False
                                        yield content
                                except json.JSONDecodeError:
                                    continue
                        return # Success
                    else:
                        print(f"⚠️ Groq Status {response.status_code}")
                        
        except (httpx.NetworkError, httpx.TimeoutException) as e:
            print(f"⚠️ Groq Network error: {e}. Waiting for internet...")
            await wait_for_internet_helper()
        except Exception as e:
            print(f"⚠️ Groq Path failed: {e}")
            await asyncio.sleep(1)

    # === PATH 2: FINAL SAFETY FALLBACK (OpenRouter) ===
    print("🆘 [SAFETY-FALLBACK] Groq unavailable. Using OpenRouter...")
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"}
        payload = {
            "model": "google/gemini-2.0-flash-001",
            "messages": [{"role": "user", "content": prompt}],
            "stream": True
        }
        
        async with httpx.AsyncClient(timeout=20.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as res:
                if res.status_code == 200:
                    async for line in res.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                chunk = json.loads(line[6:])
                                content = chunk["choices"][0]["delta"].get("content", "")
                                if content: yield content
                            except: pass
                else:
                    yield f"Alex is having trouble connecting (Status {res.status_code})."
    except Exception as e:
        yield f"Critical Error: Alex is offline. {e}"

# === Assets (Simplified) === #
def generate_image_asset(prompt, user_keys=None):
    return None

def generate_ebook_theme(topic, description="", user_keys=None):
    return {
        "primary_rgb": [20, 20, 20], 
        "secondary_rgb": [200, 0, 0], 
        "layout_mode": "Sophisticated",
        "visual_style": "Cinematic"
    }

