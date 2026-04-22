import os
import chromadb
from chromadb.config import Settings
import datetime
import json
import uuid

class MemoryManager:
    def __init__(self, db_path="./memory_db"):
        self.db_path = db_path
        if not os.path.exists(self.db_path):
            os.makedirs(self.db_path)
            
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.client.get_or_create_collection(name="alex_memory")
        self.profile_collection = self.client.get_or_create_collection(name="user_profile")
        
        # Current conversation buffer (transient but persisted to file)
        self.session_id = str(uuid.uuid4())[:8]
        self.session_cache_file = "session_cache.json"
        self.session_history = self._load_session_cache()

    def _load_session_cache(self):
        """Loads the session history from a local JSON file to survive restarts."""
        if os.path.exists(self.session_cache_file):
            try:
                with open(self.session_cache_file, "r") as f:
                    data = json.load(f)
                    self.session_id = data.get("session_id", self.session_id)
                    return data.get("history", [])
            except: pass
        return []

    def _save_session_cache(self):
        """Saves current session history to disk."""
        try:
            with open(self.session_cache_file, "w") as f:
                json.dump({"session_id": self.session_id, "history": self.session_history}, f)
        except: pass

    def start_new_session(self):
        """Resets the session ID and clears the cache for a fresh start."""
        print("🧹 [MEMORY] Starting fresh session...")
        self.session_id = str(uuid.uuid4())[:8]
        self.session_history = []
        if os.path.exists(self.session_cache_file):
            os.remove(self.session_cache_file)

    def save_chat(self, user_text, alex_response):
        """Saves conversations into the 3-Layer architecture."""
        # 1. Update Layer 1 (Absolute Session Flow)
        turn = {"user": user_text, "assistant": alex_response}
        self.session_history.append(turn)
        if len(self.session_history) > 12: # Keep 12 for robust flow
            self.session_history.pop(0)
        self._save_session_cache()

        # 2. Update Long-Term (Layers 2 & 3)
        # Filter junk, but save everything else for semantic search
        junk_patterns = ["hi", "hello", "ok", "yes", "no", "bye", "wait", "alex"]
        if len(user_text) < 3 or (user_text.lower().strip() in junk_patterns):
            return 

        timestamp = datetime.datetime.now().isoformat()
        content = f"User: {user_text}\nAssistant: {alex_response}"
        
        # Add with session_id metadata for Layer 2 filtering
        self.collection.add(
            documents=[content],
            metadatas=[{"timestamp": timestamp, "session_id": self.session_id}],
            ids=[f"chat_{timestamp}_{uuid.uuid4().hex[:6]}"]
        )

    def get_user_profile(self):
        """Retrieves the permanent distilled profile of the user."""
        try:
            res = self.profile_collection.get(ids=["master_profile"])
            if res['documents']: return res['documents'][0]
        except: pass
        return "A user interested in various topics."

    def update_user_profile(self, user_text, alex_response, api_key):
        """Update the bio-profile (kept simple for efficiency)."""
        import requests
        value_markers = ["name", "am a", "work", "love", "hate", "from", "expert", "prefer"]
        if not any(v in user_text.lower() for v in value_markers) and len(user_text) < 40:
            return 

        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            old_profile = self.get_user_profile()
            prompt = f"Profile: {old_profile}\nNew context: {user_text} -> {alex_response}\nUpdate profile concisely (1-2 sentences):"
            payload = {"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "max_tokens": 80}
            res = requests.post(url, headers=headers, json=payload, timeout=3)
            if res.status_code == 200:
                new_profile = res.json()["choices"][0]["message"]["content"].strip()
                self.profile_collection.upsert(documents=[new_profile], ids=["master_profile"])
        except: pass

    def recall_memory(self, query):
        """Retrieves using the 3-Layer Hierarchical strategy."""
        context_parts = []
        
        # --- LAYER 1: Immediate Session Flow (Persistent) ---
        if self.session_history:
            flow = "--- RECENT FLOW ---\n"
            for turn in self.session_history[-8:]: # Last 8 turns
                flow += f"User: {turn['user']}\nAlex: {turn['assistant']}\n"
            context_parts.append(flow)

        # --- LAYER 2: Semantic Matching (Current Session Only) ---
        try:
            # Query ONLY the current session ID
            res2 = self.collection.query(
                query_texts=[query], 
                n_results=3,
                where={"session_id": self.session_id}
            )
            if res2['documents'] and res2['documents'][0]:
                l2 = "--- RELEVANT TO CURRENT SESSION ---\n"
                found = False
                for doc, dist in zip(res2['documents'][0], res2['distances'][0]):
                    if dist < 0.7:
                        l2 += doc + "\n"
                        found = True
                if found: context_parts.append(l2)
        except: pass

        # --- LAYER 3: Cross-Session Semantic Matching (All History) ---
        try:
            # Query everything, but filter out current session to avoid duplicates
            res3 = self.collection.query(
                query_texts=[query],
                n_results=2,
                where={"session_id": {"$ne": self.session_id}}
            )
            if res3['documents'] and res3['documents'][0]:
                l3 = "--- RELEVANT PAST KNOWLEDGE (OTHER SESSIONS) ---\n"
                found = False
                for doc, dist in zip(res3['documents'][0], res3['distances'][0]):
                    if dist < 0.55: # Stricter for long-term consistency
                        l3 += doc + "\n"
                        found = True
                if found: context_parts.append(l3)
        except: pass

        return "\n\n".join(context_parts)
