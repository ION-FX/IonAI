import os
import ollama
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal
import re

# We import your existing prompt
try:
    from system_prompts import ION_AI_PRO_PROMPT
except ImportError:
    ION_AI_PRO_PROMPT = "You are a helpful AI assistant."

TOOL_CALL_REGEX = re.compile(r"\[\[(.*?)\]\]")

class LocalAIWorker(QObject):
    # Keep signals identical to your original worker so main.py doesn't break
    streaming_chunk = pyqtSignal(str)
    tool_call_requested = pyqtSignal(str, str)
    generation_done = pyqtSignal()
    error_occurred = pyqtSignal(str)
    image_generated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.is_configured = True # It's local, so it's always ready
        self.chat_history = []

        # We start with the System Prompt in history
        self.chat_history.append({'role': 'system', 'content': ION_AI_PRO_PROMPT})

        self.last_user_prompt = ""

        # Models
        self.text_model = "gemma3:27b-cloud"  # The one we just trained!
        self.vision_model = "llava" # The local eyes

    def _parse_tool_call(self, text_content):
        try:
            # Clean up potential markdown clutter from local models
            text_content = text_content.replace('`', '').strip()

            parts = text_content.split(":", 1)
            tool_name = parts[0].strip()
            tool_args = parts[1].strip() if len(parts) > 1 else ""
            return tool_name, tool_args
        except Exception as e:
            print(f"Error parsing tool call: {e}")
            return None

    def _send_message_and_process(self, text_to_send, is_vision_response=False):
        """
        Sends text to Local Ollama.
        """
        try:
            # 1. Append User Message to History
            self.chat_history.append({'role': 'user', 'content': text_to_send})

            # 2. Stream Response
            # We use the 'jarvis' model we trained
            stream = ollama.chat(
                model=self.text_model,
                messages=self.chat_history,
                stream=True
            )

            full_text = ""

            # 3. Process the Stream
            for chunk in stream:
                content = chunk['message']['content']
                self.streaming_chunk.emit(content)
                full_text += content

            full_text = full_text.strip()

            # 4. Append Assistant Response to History
            self.chat_history.append({'role': 'assistant', 'content': full_text})

            # 5. Check for Tools
            # Local models sometimes hallucinate extra brackets, so regex is key
            tool_calls_found = TOOL_CALL_REGEX.findall(full_text)

            if tool_calls_found:
                # We take the first tool found
                first_call_content = tool_calls_found[0]
                parsed = self._parse_tool_call(first_call_content)
                if parsed:
                    self.tool_call_requested.emit(parsed[0], parsed[1])

            self.generation_done.emit()

        except Exception as e:
            self.error_occurred.emit(f"Ollama Error: {e}")

    def _process_vision_request(self, image_path):
        """
        Uses Local 'Llava' to analyze the image.
        """
        try:
            print(f"AI Worker: Delegating vision task to Local Llava...")

            vision_prompt = (
                f"The user asked: '{self.last_user_prompt}'. "
                f"Analyze this image. If you find UI elements or text relevant to the request, "
                f"describe them and their approximate location."
            )

            # Llava call (Stateless, we don't need history for this)
            res = ollama.chat(
                model=self.vision_model,
                messages=[{
                    'role': 'user',
                    'content': vision_prompt,
                    'images': [image_path]
                }]
            )

            vision_text = res['message']['content']
            print(f"Vision Result: {vision_text[:100]}...")

            # Feed result back to Jarvis
            formatted_for_jarvis = (
                f"System [Vision Report]: I analyzed the screen using Llava. "
                f"Findings:\n{vision_text}\n"
                f"Use this to answer the user."
            )

            self._send_message_and_process(formatted_for_jarvis, is_vision_response=True)

        except Exception as e:
            print(f"Vision Error: {e}")
            self.error_occurred.emit(f"Vision Error: {e}")

    # === SLOTS ===

    @pyqtSlot(str)
    def generate_response(self, user_prompt):
        self.last_user_prompt = user_prompt
        self._send_message_and_process(user_prompt)

    @pyqtSlot(str)
    def handle_tool_result(self, tool_output_text):
        # CASE 1: RAW SCREENSHOT (Input)
        if tool_output_text.startswith("IMAGE_PATH:"):
            image_path = tool_output_text.replace("IMAGE_PATH:", "").strip()
            self._process_vision_request(image_path)

        # CASE 2: ANNOTATED IMAGE (Output)
        elif tool_output_text.startswith("ANNOTATED_PATH:"):
            final_image_path = tool_output_text.replace("ANNOTATED_PATH:", "").strip()
            self.image_generated.emit(final_image_path)
            formatted_output = "System: Annotation displayed on HUD. Task complete."
            self._send_message_and_process(formatted_output)

        # CASE 3: TEXT RESULT
        else:
            formatted_output = f"Tool Result: {tool_output_text}"
            self._send_message_and_process(formatted_output)
