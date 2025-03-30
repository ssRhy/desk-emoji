from openai import OpenAI
import requests
import json
import os

from common import *
from connect import *


class GPT(BaseLLM):

    def __init__(self):
        super().__init__("GPT")
        self.json_path = 'gpt_api.json'
        self.provider = "siliconflow"  # 默认使用硅基流动
        self.is_proxy_api = True  # 默认设为中转API
        self._create_empty_json()

    def _create_empty_json(self):
        if not os.path.exists(self.json_path):
            with open(self.json_path, 'w') as f:
                # 设置默认值为硅基流动API
                json.dump({
                    "api_url": "https://api.siliconflow.cn/v1/chat/completions", 
                    "api_key": "", 
                    "provider": "siliconflow", 
                    "model": "Qwen/QwQ-32B"
                }, f)

    def write_json(self, api_url, api_key, model="", provider="openai"):
        with open(self.json_path, 'w') as f:
            json.dump({"api_url": api_url, "api_key": api_key, "provider": provider, "model": model}, f)

    def read_json(self):
        try:
            with open(self.json_path, 'r') as f:
                data = json.load(f)
                self.provider = data.get("provider", "openai")
                self.model = data.get("model", "")
                return data.get("api_url", ""), data.get("api_key", "")
        except Exception as e:
            error(e, f"Failed to read {self.json_path}")
            return "", ""

    def connect(self, api_url="", api_key=""):
        if not api_url or not api_key:
            api_url, api_key = self.read_json()
            
        self.api_url = api_url
        self.api_key = api_key
        self.is_proxy_api = True  # 标记为中转API
        
        # 测试连接
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model or "Qwen/QwQ-32B",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 5,
                "temperature": 0.7,
                "top_p": 0.7,
                "stream": False
            }
            
            logger.info(f"Testing connection to: {self.api_url}")
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Connect to Silicon Flow API Success! Response: {result}")
                return True
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                error(error_msg, "Connect to API Failed! Please check the API configuration")
                return False
        except Exception as e:
            error(e, "Connect to API Failed! Please check the API configuration")
            return False

    def chat(self, message='', model="", temperature=0.7):
        if not model and hasattr(self, 'model') and self.model:
            model = self.model
        if not model:  # 如果还是没有模型，使用默认值
            model = "Qwen/QwQ-32B"
        
        messages = [{"role": "system", "content": llm_role},
                    {"role": "user", "content": llm_prompt + message}]
        
        # 使用直接的 HTTP 请求
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 512,
            "top_p": 0.7,
            "top_k": 50,
            "frequency_penalty": 0.5,
            "n": 1,
            "response_format": {"type": "text"},
            "stream": False
        }
        
        logger.info(f"Sending request to {self.api_url} with model {model}")
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.debug(f"Raw API response: {result}")
                
                if "choices" in result and len(result["choices"]) > 0 and "message" in result["choices"][0]:
                    answer_text = result["choices"][0]["message"].get("content", "").strip()
                    if not answer_text:
                        answer_text = "API返回了空响应，请检查模型配置或重试。"
                        logger.warning("Received empty response content from API")
                else:
                    answer_text = f"API返回了非标准格式: {result}"
                    logger.warning(f"Unexpected API response format: {result}")
                
                return json.dumps({"answer": answer_text})
            else:
                error_msg = f"API请求失败: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return json.dumps({"answer": error_msg})
        except Exception as e:
            error_msg = f"请求错误: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"answer": error_msg})

    def speech(self, model="whisper-1", audio_path=""):
        if self.provider == "openai":
            audio_file= open(audio_path, "rb")
            transcription = self.client.audio.transcriptions.create(
                model=model,
                file=audio_file
            )
            return transcription.text
        elif self.provider == "deepseek":
            # DeepSeek 可能有不同的语音识别 API，这里需要根据 DeepSeek 的 API 文档进行调整
            # 以下是示例代码，需要根据实际 API 进行修改
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            with open(audio_path, "rb") as audio_file:
                files = {"file": audio_file}
                response = requests.post(
                    f"{self.api_url.split('/chat/completions')[0]}/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data={"model": model}
                )
            if response.status_code == 200:
                return response.json().get("text", "")
            else:
                error_msg = f"DeepSeek Speech API Error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return ""
        else:
            error_msg = f"Speech not supported for provider: {self.provider}"
            logger.error(error_msg)
            return ""

    def speak(self, text="", model="tts-1", voice="onyx", audio_path=""):
        if self.provider == "openai":
            response = self.client.audio.speech.create(
                model=model,
                voice=voice,
                input=text
            )
            logger.info(f"Voice: {voice}")
            response.stream_to_file(audio_path)
        elif self.provider == "deepseek":
            # DeepSeek 可能有不同的语音合成 API，这里需要根据 DeepSeek 的 API 文档进行调整
            # 以下是示例代码，需要根据实际 API 进行修改
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            payload = {
                "model": model,
                "voice": voice,
                "input": text
            }
            response = requests.post(
                f"{self.api_url.split('/chat/completions')[0]}/audio/speech",
                headers=headers,
                json=payload
            )
            if response.status_code == 200:
                with open(audio_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"Voice: {voice}")
            else:
                error_msg = f"DeepSeek TTS API Error: {response.status_code} - {response.text}"
                logger.error(error_msg)
        else:
            error_msg = f"TTS not supported for provider: {self.provider}"
            logger.error(error_msg)


if __name__ == '__main__':
    blt = BluetoothClient()
    llm = GPT()
    llm.connect()
    # 测试代码 (已省略)