import os
import time
import asyncio
import re
import pyaudio
import numpy as np
import speech_recognition as sr
import edge_tts
import audioop
import glob
import subprocess
import signal
import sys
import atexit
from ai_helper import generate_ai_response_stream
from memory_manager import MemoryManager
from dotenv import load_dotenv

load_dotenv()

def check_internet():
    """Quick check for internet connectivity (DNS based first, then HTTP)."""
    import socket
    try:
        # Check DNS first (fastest)
        socket.setdefaulttimeout(1)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except:
        try:
            import requests # Fallback for restricted networks
            requests.get("https://www.google.com", timeout=2)
            return True
        except:
            return False

async def wait_for_internet(assistant=None):
    """Wait until internet is restored, notifying the user if possible."""
    if check_internet():
        return True
    
    print("\n📡 [OFFLINE] Internet lost. Alex is standing by...")
    while not check_internet():
        await asyncio.sleep(3)
    
    print("✅ [ONLINE] Internet restored. Resuming...")
    return True

def cleanup_old_speech_files():
    """Removes any leftover speech files from previous sessions."""
    for f in glob.glob("speech_*.mp3"):
        try: os.remove(f)
        except: pass
    print("🧹 [CLEANUP] Old speech files removed.")

cleanup_old_speech_files()

# --- CONFIGURATION ---
WAKE_WORD = "alex"
STOP_WORDS = ["bye alex", "by alex"]
NEW_CONV_WORD = "new conversation"
SILENCE_DURATION = 1.8      # Snappier cutoff (from 2.1)
VOICE = "en-GB-RyanNeural"
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
MIN_VOCAL_FRAMES = 5       # Filter out clicks/noise pops (from 3)
THRESHOLD_MULTIPLIER = 2.0 # Safer margin against room noise (from 1.3)
THRESHOLD_CAP = 5000        # Allow room for loud mics/noise

class AlexAssistant:
    def __init__(self):
        self.memory = MemoryManager()
        self.recognizer = sr.Recognizer()
        self.is_active = False
        self.is_speaking = False
        self.is_processing = False # New: Thinking/Research flag
        self.playback_queue = None
        self.dynamic_threshold = 300
        self.noise_buffer = [] # Layer for real-time noise adaptation
        self.running = True
        
        # 🎙️ [PERSISTENT AUDIO]
        self.p = pyaudio.PyAudio()
        self.stream = None
        
        # Register signal handlers for clean exit
        signal.signal(signal.SIGINT, self.handle_exit_signal)
        signal.signal(signal.SIGTERM, self.handle_exit_signal)
        
        atexit.register(self.cleanup)

        # System Prompt
        self.system_prompt = """Act like a blunt, hyper-efficient human. Your goal is to deliver facts as fast as possible.
        
Rules:
1. Start with a direct, 1-line answer.
2. NO ANALOGIES for simple facts or common sense.
3. Use an analogy ONLY if explaining a truly complex technical concept that requires it.
4. If it's a 'yes/no' or simple fact, just state it. Don't explain 'why' unless asked.
5. Max 2 lines total. Stop the moment the fact is delivered.
6. Absolute efficiency. No fluff, no metaphors, no 'think of it as...' for basic stuff."""

    def cleanup(self):
        """Ensures PyAudio and streams are closed on any exit."""
        if hasattr(self, 'stream') and self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except: pass
            self.stream = None
        if hasattr(self, 'p') and self.p:
            try: self.p.terminate()
            except: pass
            self.p = None
        print("🟢 [CLEANUP] Microphone released and PortAudio terminated.")

    def handle_exit_signal(self, sig, frame):
        """Standard signal handler for SIGTERM and SIGINT."""
        print(f"\n🛑 [STOP] Signal {sig} received. Alex shutting down clean...")
        self.running = False
        self.cleanup() # Instant hardware release
        sys.exit(0) # Break loops and exit

    async def generate_speech_chunk(self, text, index):
        """Generates a single speech chunk file. Skips if text is empty/invalid."""
        if not text or not text.strip() or len(text.strip()) < 1:
            return None
            
        # Clean text of characters edge-tts might dislike
        clean_text = re.sub(r'[^\w\s.,?!]', '', text.strip())
        if not clean_text: return None

        tmp_file = f"speech_{index}_{int(time.time())}.mp3"
        
        while self.running:
            try:
                communicate = edge_tts.Communicate(clean_text, VOICE)
                await communicate.save(tmp_file)
                return tmp_file
            except Exception as e:
                print(f"⚠️ Synthesis failed for chunk {index}: {e}. Retrying when online...")
                if not check_internet():
                    await wait_for_internet(self)
                else:
                    # If internet is technically up but synthesis still fails, wait a bit
                    await asyncio.sleep(2)
        return None

    async def playback_worker(self):
        """Worker that plays audio chunks and prints text in sync."""
        while True:
            text, tmp_file = await self.playback_queue.get()
            self.is_speaking = True
            try:
                # Print the text Alex is currently speaking
                print(f"\n🗣️ [ALEX]: {text}")
                
                # Use native macOS afplay for high-quality, glitch-free audio
                process = await asyncio.create_subprocess_exec("afplay", tmp_file)
                await process.wait()
            finally:
                # Cleanup temporary file immediately after use
                if os.path.exists(tmp_file) and tmp_file != "activation.mp3":
                    try: os.remove(tmp_file)
                    except: pass
                self.playback_queue.task_done()
                if self.playback_queue.empty():
                    self.is_speaking = False

    async def stream_and_synthesize(self, user_text, raw_query=None):
        """Streams AI response, splits into sentences, and queues audio."""
        if not check_internet():
            print(">> Alex needs internet to think. Waiting...")
            await wait_for_internet(self)

        user_profile = self.memory.get_user_profile()
        context = self.memory.recall_memory(user_text)
        
        # Inject Profile into System Prompt for Adaptive Explanations
        adaptive_prompt = f"{self.system_prompt}\n\nUSER PROFILE: You are talking to {user_profile}. Adapt your language and analogies to their expertise level and background."
        prompt = f"{adaptive_prompt}\n\nContext:\n{context}\n\nUser: {user_text}"
        
        sentence_buffer = ""
        sentence_index = 0
        full_response = ""
        
        async for chunk in generate_ai_response_stream(prompt, raw_query=raw_query):
            full_response += chunk
            sentence_buffer += chunk
            
            if any(p in chunk for p in ".?!"):
                sentences = re.split(r'(?<=[.?!])\s+', sentence_buffer.strip())
                if len(sentences) > 1 or sentence_buffer.strip().endswith(('.', '?', '!')):
                    for s in sentences[:-1] if not sentence_buffer.strip().endswith(('.', '?', '!')) else sentences:
                        if s.strip():
                            audio_file = await self.generate_speech_chunk(s.strip(), sentence_index)
                            if audio_file:
                                await self.playback_queue.put((s.strip(), audio_file))
                                sentence_index += 1
                    sentence_buffer = sentences[-1] if not sentence_buffer.strip().endswith(('.', '?', '!')) else ""

        if sentence_buffer.strip():
            audio_file = await self.generate_speech_chunk(sentence_buffer.strip(), sentence_index)
            if audio_file:
                await self.playback_queue.put((sentence_buffer.strip(), audio_file))
        
        self.memory.save_chat(user_text, full_response)
        
        # Periodically update the user profile in the background (Non-blocking)
        # Note: We pass the Groq key for the distillation LLM
        groq_key = os.environ.get("GROQ_API_KEY")
        asyncio.create_task(asyncio.to_thread(self.memory.update_user_profile, user_text, full_response, groq_key))

    def manual_listen(self):
        """Strict 5-second silence rule manual VAD (0.8s for wake-word for instant feel)."""
        # 🎙️ Use persistent PyAudio instance
        if not self.p: self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE, input=True, frames_per_buffer=CHUNK_SIZE)
        
        # Split silence for better UX: 0.8s for name trigger, 5s for talking
        required_silence = 0.8 if not self.is_active else SILENCE_DURATION
        
        if not self.is_active:
            print("Listening for wake word...")
        
        frames = []
        has_spoken = False
        silence_start = None
        start_time = time.time()
        vocal_count = 0  # To filter out short noise pops
        
        try:
            while self.running:
                data = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
                
                # ECHO/PROCESSING CANCELLATION: Skip while speaking or thinking
                if self.is_speaking or self.is_processing:
                    frames = [] # Keep buffer clear
                    has_spoken = False
                    vocal_count = 0
                    continue
                    
                frames.append(data)
                rms = audioop.rms(data, 2)
                
                # 1. Detect Speech Start (with debounce & adaptive thresholding)
                if not has_spoken:
                    if rms > self.dynamic_threshold:
                        vocal_count += 1
                        if vocal_count >= MIN_VOCAL_FRAMES: 
                            if self.is_active: print(f"\n>> Voice detected (RMS: {rms:.0f})")
                            has_spoken = True
                            silence_start = None
                            self.noise_buffer = [] # Clear buffer once speaking
                    else:
                        vocal_count = 0
                        # ADAPTIVE: Track background noise when NO voice is detected
                        self.noise_buffer.append(rms)
                        if len(self.noise_buffer) > 15: # ~0.5s of audio
                            self.noise_buffer.pop(0)
                            avg_noise = sum(self.noise_buffer) / len(self.noise_buffer)
                            new_thresh = min(max(300, avg_noise * THRESHOLD_MULTIPLIER), THRESHOLD_CAP)
                            
                            # Only update if shift is significant (>15%) to avoid jitter
                            if abs(new_thresh - self.dynamic_threshold) / (self.dynamic_threshold + 1e-6) > 0.15:
                                self.dynamic_threshold = new_thresh
                                if self.is_active:
                                    print(f"\r[ADAPTIVE] Noise floor shift. New Threshold: {self.dynamic_threshold:.0f}  ", end="", flush=True)
                
                # 2. Only if speaking has started, handle silence timer
                else:
                    if rms > self.dynamic_threshold:
                        silence_start = None # Reset timer if user speaks again
                    else:
                        if silence_start is None:
                            silence_start = time.time()
                        
                        elapsed_silence = time.time() - silence_start
                        if self.is_active:
                            print(f"\rRMS: {rms:.0f} | Silence: {elapsed_silence:.1f}s/{required_silence:.1f}s  ", end="", flush=True)
                        
                        if elapsed_silence >= required_silence:
                            if self.is_active: print(f"\n>> Finished speaking after {required_silence}s.")
                            break
                            
                # Idle timeout (only before speech starts)
                if not has_spoken and time.time() - start_time > 25:
                    break
        finally:
            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except: pass
                self.stream = None
            # Do NOT terminate self.p here, keep it for the next listen

        if not has_spoken:
            return ""

        audio_data = sr.AudioData(b"".join(frames), SAMPLE_RATE, 2)
        
        while self.running:
            try:
                # 🛡️ [BULLETPROOF]: Google recognition requires internet
                text = self.recognizer.recognize_google(audio_data).lower()
                if self.is_active: print(f"Heard: {text}")
                return text
            except sr.UnknownValueError:
                if self.is_active: print("⚠️ [RECOGNITION] Speech detected but not understood.")
                return ""
            except sr.RequestError as e:
                if not self.is_active: return "" # Don't bother retrying if not active
                
                print(f"\n📡 [OFFLINE] Google Recognition Error: {e}")
                print(">> Alex is waiting for internet to recover...")
                # Loop until internet is back or system shuts down
                while self.running and not check_internet():
                    time.sleep(2)
                
                if not self.running: return ""
                print("🔄 [RETRYING] Connection restored. Processing buffered query...")
                # Continue loop to next attempt of recognize_google
            except Exception as e:
                if self.is_active: print(f"⚠️ Recognition error: {e}")
                return ""

    async def calibrate(self):
        """One-time noise calibration and pre-cache activation sound."""
        print(">> Calibrating noise floor... (stay quiet)")
        if not self.p: self.p = pyaudio.PyAudio()
        stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE, input=True, frames_per_buffer=CHUNK_SIZE)
        noise_samples = []
        for _ in range(15):
            d = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            noise_samples.append(audioop.rms(d, 2))
        stream.stop_stream()
        stream.close()
        avg_noise = sum(noise_samples) / len(noise_samples)
        print(f">> Noise floor detected: {avg_noise:.0f} RMS")
        calculated_thresh = avg_noise * THRESHOLD_MULTIPLIER
        self.dynamic_threshold = min(max(150, calculated_thresh), THRESHOLD_CAP)
        
        # PRE-CACHE ACTIVATION SOUND
        if not os.path.exists("activation.mp3"):
            communicate = edge_tts.Communicate("Yes", VOICE)
            await communicate.save("activation.mp3")
            
        print(f">> Calibration complete. Threshold set to: {self.dynamic_threshold:.0f}")

    async def run(self):
        print("--- Alex AI System (Instant Response Mode) Active ---")
        await self.calibrate()
        self.playback_queue = asyncio.Queue()
        asyncio.create_task(self.playback_worker())
        
        while self.running:
            # PRE-FLIGHT INTERNET CHECK: Don't even listen if offline
            if not check_internet():
                await wait_for_internet(self)

            if not self.is_speaking:
                text = await asyncio.to_thread(self.manual_listen)
                
                if not text:
                    continue

                # 1. Handle "New Conversation" first (High Priority)
                if "new conversation" in text.lower() or "reset session" in text.lower():
                    self.is_active = True # Auto-activate if command is given
                    self.memory.start_new_session()
                    msg = "Starting a fresh session. How can I help?"
                    audio = await self.generate_speech_chunk(msg, 998)
                    if audio: await self.playback_queue.put((msg, audio))
                    continue

                if any(sw in text for sw in STOP_WORDS):
                    self.is_active = False
                    print(">> Alex standby (spoken)")
                    msg = "See you later."
                    audio = await self.generate_speech_chunk(msg, 999)
                    if audio: await self.playback_queue.put((msg, audio))
                    continue

                # 3. Handle Wake Word activation & Command Parsing
                if WAKE_WORD in text:
                    was_already_active = self.is_active
                    if not was_already_active:
                        self.is_active = True
                        print(">> Alex activated (Instant Yes)")
                        await self.playback_queue.put(("Yes", "activation.mp3"))
                    
                    # Extract the command following the wake word
                    # Using regex to split at the wake word ensures we catch "Alex, [command]"
                    parts = re.split(rf"\b{WAKE_WORD}\b", text, flags=re.IGNORECASE, maxsplit=1)
                    command_part = parts[1].strip() if len(parts) > 1 else ""
                    
                    # Clean up leading punctuation/garbage (e.g., "Alex, help" -> ", help" -> "help")
                    command_part = re.sub(r"^[^\w]+", "", command_part).strip()
                    
                    if not command_part:
                        # Just the wake word was spoken, or word was at the end
                        if not was_already_active:
                            continue # Wait for next utterance
                        else:
                            # If already active and they just said "Alex", maybe don't 
                            # just continue, but for now we'll allow it.
                            continue

                    # If there's a command following the name, use it!
                    text = command_part
                
                if not self.is_active:
                    continue

                # 4. Start AI Response
                print("📡 [ALEX] Thinking...")
                self.is_processing = True
                api_start = time.time()
                await self.stream_and_synthesize(text, raw_query=text)
                print(f"✅ [ALEX] Response complete. (Total Latency: {time.time() - api_start:.2f}s)")
                
                # Turn off processing but wait for playback to finish
                while self.is_speaking:
                    await asyncio.sleep(0.1)
                
                self.is_processing = False
                await asyncio.sleep(2.0) # Safety cooldown after reply (from 1.0)
            else:
                await asyncio.sleep(0.1)

if __name__ == "__main__":
    while True: # 🛡️ [24/7 BULLETPROOF LOOP]
        try:
            assistant = AlexAssistant()
            asyncio.run(assistant.run())
            
            # If run() returns naturally, check if it was a signal shutdown
            if not assistant.running:
                break
                
        except Exception as e:
            print(f"🔥 [CRITICAL] System crashed: {e}. Self-healing in 5s...")
            time.sleep(5)
        except (KeyboardInterrupt, SystemExit):
            print("\n👋 [EXIT] Alex shutting down.")
            break
