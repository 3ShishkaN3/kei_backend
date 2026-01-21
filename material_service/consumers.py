import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from .models import Test, AiConversationQuestion, TestSubmission, AiConversationSubmissionAnswer
from lesson_service.models import SectionItem
from django.utils import timezone
import asyncio
import google.generativeai as genai
from channels.db import database_sync_to_async
import aiohttp
import ssl
import certifi

logger = logging.getLogger(__name__)
genai.configure(api_key=settings.GEMINI_API_KEY)

GEMINI_WS_URL = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={settings.GEMINI_API_KEY}"
GEMINI_NATIVE_AUDIO_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"

class AiConversationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.test_id = self.scope['url_route']['kwargs']['test_id']
        self.user = self.scope.get("user")

        logger.info(f"Connecting AI Conversation. User: {self.user}, Auth: {self.user.is_authenticated if self.user else 'No User'}")
        
        if not self.user or self.user.is_anonymous:
            headers = dict(self.scope.get('headers', []))
            logger.warning(f"Anonymous user tried to connect. Headers: {headers.get(b'cookie', b'No cookies')}")
            if not settings.DEBUG:
                await self.close()
                return
            else:
                logger.info("Allowing anonymous connection because DEBUG=True")

        try:
            self.test = await self.get_test(self.test_id)
            self.question_config = await self.get_question_config(self.test)
        except Exception as e:
            logger.error(f"Error connecting to AI Conversation: {e}")
            await self.close()
            return

        self.conversation_history = []
        self.gemini_ws = None
        self.gemini_session = None
        self.receiver_task = None
        self.gemini_ready = False
        self.not_ready_notified = False
        self.start_requested = False
        self.intro_sent = False
        self.current_ai_text = ""
        self.translation_task = None
        
        personality = self.question_config.personality or "Кей-сенпай"
        context = self.question_config.context
        goodbye = self.question_config.goodbye_condition or "Попрощайся и закончи разговор, когда цели достигнуты."
        
        self.system_instruction = f"""
        Ты — {personality}. Твой характер: аниме-тян, преподаватель японского языка.
        ОБЯЗАТЕЛЬНОЕ УСЛОВИЕ: Твои ответы должны быть СТРОГО на японском языке. Ни слова по-русски или по-английски.
        КОНТЕКСТ РАЗГОВОРА: {context}
        {goodbye}
        
        Когда разговор должен быть закончен, добавь в конце сообщения тег [FINISH].
        Будь лаконичным, пиши естественно и коротко.
        """
        
        await self.accept()
        await self.init_gemini_live()

    async def init_gemini_live(self):
        try:
            logger.info(f"Targeting Gemini Socket: {GEMINI_WS_URL}")
            
            timeout = aiohttp.ClientTimeout(total=30)
            self.gemini_session = aiohttp.ClientSession(timeout=timeout)
            
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            self.gemini_ws = await self.gemini_session.ws_connect(GEMINI_WS_URL, ssl=ssl_context)
            logger.info("WS Connected. Sending setup...")
            
            setup_msg = {
                "setup": {
                    "model": GEMINI_NATIVE_AUDIO_MODEL,
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "candidateCount": 1,
                        "speechConfig": {
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {"voiceName": "Aoede"}
                            }
                        }
                    },
                    "systemInstruction": {
                        "role": "system",
                        "parts": [{"text": self.system_instruction.strip()}]
                    }
                }
            }
            await self.gemini_ws.send_json(setup_msg)
            
            self.receiver_task = asyncio.create_task(self.receive_from_gemini())
            logger.info("Gemini Live initialized and setup sent.")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini Live: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to connect to Gemini Live'
            }))

    async def receive_from_gemini(self):
        try:
            async for msg in self.gemini_ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_gemini_message(json.loads(msg.data))

                elif msg.type == aiohttp.WSMsgType.BINARY:
                    data_preview = msg.data[:200]
                    try:
                        decoded = msg.data.decode('utf-8')
                    except Exception:
                        decoded = None
                    if decoded:
                        try:
                            await self._handle_gemini_message(json.loads(decoded))
                        except Exception as err:
                            logger.warning(f"Failed to parse binary message from Gemini: {err}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error('Gemini WS closed with error %s' % self.gemini_ws.exception())
                    await self._handle_gemini_disconnect('Голосовой канал сенсея отключился. Переподключаемся...')
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    await self._handle_gemini_disconnect('Сенсей потерял связь и пытается переподключиться...')
                    break
                else:
                    logger.warning(f"Gemini WS non-text message type {msg.type}. Data length: {len(msg.data) if hasattr(msg.data, '__len__') else 'N/A'}")
        except Exception as e:
            logger.error(f"Error in receive_from_gemini: {e}")
        finally:
            logger.info("Stopped receiving from Gemini.")
            self.gemini_ready = False
            self.not_ready_notified = False

    async def disconnect(self, close_code):
        if self.receiver_task:
            self.receiver_task.cancel()
        if self.gemini_ws:
            await self.gemini_ws.close()
        if self.gemini_session:
            await self.gemini_session.close()
            
        if hasattr(self, 'conversation_history') and self.conversation_history:
            await self.save_submission()

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            data = json.loads(text_data)
            
            if data.get('action') == 'submit_for_evaluation':
                await self.save_submission()
                await self.send(text_data=json.dumps({
                    'type': 'evaluation_submitted'
                }))
                await self.close()
                return
            if data.get('action') == 'start':
                self.start_requested = True
                await self._maybe_send_intro()
                return

            message = data.get('message')
            if message:
                if not await self._ensure_gemini_ready():
                    return
                if self.gemini_ws and not self.gemini_ws.closed:
                    try:
                        payload = {
                            "clientContent": {
                                "turns": [{
                                    "role": "user",
                                    "parts": [{"text": message}]
                                }],
                                "turnComplete": True
                            }
                        }
                        await self.gemini_ws.send_json(payload)
                        self.conversation_history.append({"role": "user", "content": message})
                    except Exception as e:
                        logger.error(f"Error sending text to Gemini: {e}")
        
        if bytes_data:
            if not await self._ensure_gemini_ready():
                return
            if self.gemini_ws and not self.gemini_ws.closed:
                try:
                    import base64
                    b64_data = base64.b64encode(bytes_data).decode('utf-8')
                    await self.gemini_ws.send_json({
                        "realtimeInput": {
                            "mediaChunks": [{
                                "data": b64_data,
                                "mimeType": "audio/pcm;rate=16000"
                            }]
                        }
                    })
                except Exception as e:
                    logger.error(f"Error sending audio to Gemini: {e}")
            else:
                logger.error("Gemini Socket Closed or None during AUDIO receive!")
                await self._handle_gemini_disconnect('Сенсей отключился. Перезапустите разговор.')

    async def _handle_gemini_message(self, data):
        if not data:
            return

        if "setupComplete" in data:
            logger.info("Gemini Live Setup Complete.")
            self.gemini_ready = True
            self.not_ready_notified = False
            await self.send(text_data=json.dumps({
                'type': 'ready',
                'message': 'Сенсей готов к разговору!'
            }))
            await self._maybe_send_intro()
            return

        server_content = data.get("serverContent")
        if server_content:
            model_turn = server_content.get("modelTurn")
            if model_turn:
                parts = model_turn.get("parts", [])
                for part in parts:
                    inline_data = part.get("inlineData")
                    if inline_data:
                        await self.send(text_data=json.dumps({
                            'type': 'audio_chunk',
                            'data': inline_data.get("data")
                        }))
                    text = part.get("text")
                    if text:
                        text_lower = text.lower()
                        reflection_keywords = [
                            "focusing on", "i've crafted", "i'm integrating", "the goal is",
                            "aiming for", "sticking to", "maintaining", "solidify",
                            "beginner-friendly", "contextually relevant", "i've", "i'm",
                            "crafting", "integrating", "focusing", "initiating",
                            "i am now", "my plan is", "my greeting"
                        ]
                        is_reflection = any(keyword in text_lower for keyword in reflection_keywords)
                        
                        if is_reflection or text.strip().startswith("**"):
                            logger.debug(f"Пропущено внутреннее размышление модели: {text[:100]}")
                            continue
                        
                        has_japanese = any(
                            '\u3040' <= char <= '\u309F' or  # Хирагана
                            '\u30A0' <= char <= '\u30FF' or  # Катакана
                            '\u4E00' <= char <= '\u9FAF'      # Кандзи
                            for char in text
                        )
                        
                        if len(text) > 20 and not has_japanese and text.isascii():
                            logger.debug(f"Пропущен текст без японских символов (вероятно размышление): {text[:100]}")
                            continue
                        
                        if self.conversation_history and self.conversation_history[-1]["role"] == "assistant":
                            self.conversation_history[-1]["content"] += text
                        else:
                            self.conversation_history.append({"role": "assistant", "content": text})
                        
                        await self.send(text_data=json.dumps({
                            'type': 'ai_text_chunk',
                            'text': text
                        }))
                        
                        self.current_ai_text += text
                        
                        if len(self.current_ai_text) > 50:
                            text_to_translate = self.current_ai_text
                            self.current_ai_text = ""
                            asyncio.create_task(self._send_translation_async(text_to_translate))

            if server_content.get("turnComplete"):
                if self.current_ai_text:
                    text_to_translate = self.current_ai_text
                    self.current_ai_text = ""
                    asyncio.create_task(self._send_translation_async(text_to_translate))
                
                await self.send(text_data=json.dumps({
                    'type': 'turn_complete'
                }))

        if "outputTranscription" in data:
            transcript = data["outputTranscription"].get("text")
            if transcript:
                text_lower = transcript.lower()
                reflection_keywords = [
                    "focusing on", "i've crafted", "i'm integrating", "the goal is",
                    "aiming for", "sticking to", "maintaining", "solidify",
                    "beginner-friendly", "contextually relevant", "initiating",
                    "crafting", "integrating", "focusing", "i am now", "my plan is"
                ]
                is_reflection = any(keyword in text_lower for keyword in reflection_keywords) or transcript.strip().startswith("**")
                
                if not is_reflection:
                    await self.send(text_data=json.dumps({
                        'type': 'ai_text_chunk',
                        'text': transcript
                    }))
                    self.current_ai_text += transcript
                    if len(self.current_ai_text) > 50:
                        text_to_translate = self.current_ai_text
                        self.current_ai_text = ""
                        asyncio.create_task(self._send_translation_async(text_to_translate))
                else:
                    logger.debug(f"Пропущена транскрипция (размышление): {transcript[:100]}")

        if "inputTranscription" in data:
            transcript = data["inputTranscription"].get("text")
            if transcript:
                await self.send(text_data=json.dumps({
                    'type': 'user_text_transcript',
                    'text': transcript
                }))
                asyncio.create_task(self._translate_user_speech_async(transcript))

    async def _maybe_send_intro(self):
        if self.intro_sent or not self.start_requested:
            return False
        if not await self._ensure_gemini_ready():
            return False

        intro_prompt = (
            "Поприветствуй студента, представься как Кей-сенпай и кратко начни разговор на японском, "
            "учитывая заданный контекст."
        )
        try:
            await self.gemini_ws.send_json({
                "clientContent": {
                    "turns": [{
                        "role": "user",
                        "parts": [{"text": intro_prompt}]
                    }],
                    "turnComplete": True
                }
            })
            self.intro_sent = True
            return True
        except Exception as err:
            logger.error(f"Failed to send intro prompt: {err}")
            return False

    async def get_translation(self, text):
        """Переводит японский текст на русский через gemini-2.0-flash"""
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            prompt = f"""Ты переводчик. Переведи этот японский текст на русский язык для субтитров.

ВАЖНО: 
- Переведи ТОЛЬКО на русский язык, НЕ на английский
- Переведи естественно и разговорно
- Сохрани смысл и тон

Японский текст: {text}

Перевод на русский:"""
            response = await model.generate_content_async(prompt)
            translated = response.text.strip()
            if translated.lower().startswith("перевод:"):
                translated = translated[8:].strip()
            elif translated.lower().startswith("translation:"):
                translated = translated[12:].strip()
            return translated
        except Exception as e:
            logger.warning(f"Translation error: {e}")
            return text
    
    async def translate_text_async(self, text):
        """Асинхронный перевод текста, не блокирующий основной поток"""
        if not text or len(text.strip()) < 2:
            return text
        
        try:
            translated = await self.get_translation(text)
            return translated
        except Exception as e:
            logger.warning(f"Async translation error: {e}")
            return text
    
    async def _send_translation_async(self, text):
        """Отправляет перевод текста клиенту асинхронно"""
        try:
            translated = await self.translate_text_async(text)
            await self.send(text_data=json.dumps({
                'type': 'ai_text_translated',
                'text': text,
                'translated': translated
            }))
        except Exception as e:
            logger.error(f"Error sending translation: {e}")
    
    async def _translate_user_speech_async(self, text):
        """Переводит речь ученика через gemini-2.5-flash-lite"""
        try:
            if not text or len(text.strip()) < 2:
                return
            
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            prompt = f"""Ты переводчик. Переведи этот японский текст на русский язык для субтитров.

ВАЖНО: 
- Переведи ТОЛЬКО на русский язык, НЕ на английский
- Переведи естественно и разговорно
- Сохрани смысл и тон

Японский текст: {text}

Перевод на русский:"""
            response = await model.generate_content_async(prompt)
            translated = response.text.strip()
            if translated.lower().startswith("перевод:"):
                translated = translated[8:].strip()
            elif translated.lower().startswith("translation:"):
                translated = translated[12:].strip()
            
            await self.send(text_data=json.dumps({
                'type': 'user_text_translated',
                'text': text,
                'translated': translated
            }))
        except Exception as e:
            logger.warning(f"Error translating user speech: {e}")

    @database_sync_to_async
    def get_test(self, test_id):
        return Test.objects.get(pk=test_id)

    @database_sync_to_async
    def get_question_config(self, test):
        return AiConversationQuestion.objects.get(test=test)

    @database_sync_to_async
    def save_submission(self):
        section_item = SectionItem.objects.filter(object_id=self.test.id, content_type__model='test').first()
        student = self.user if self.user and not self.user.is_anonymous else None
        if not student and not settings.DEBUG:
            return None

        submission = TestSubmission.objects.create(
            test=self.test,
            student=student,
            section_item=section_item,
            status='grading_pending',
            submitted_at=timezone.now()
        )
        
        evaluation_prompt = f"""
        Ты — опытный преподаватель японского языка. Твоя задача — оценить диалог ученика.
        КОНТЕКСТ: {self.question_config.context}
        ПРОАНАЛИЗИРУЙ ДИАЛОГ:
        {json.dumps(self.conversation_history, ensure_ascii=False)}
        ДАЙ ОЦЕНКУ по 100-балльной шкале. ВЕРНИ ТОЛЬКО JSON в формате:
        {{
            "score": число,
            "feedback": "общий отзыв"
        }}
        """
        
        try:
            grading_model = getattr(settings, 'LLM_GRADING_MODEL', 'models/gemini-2.5-flash')
            eval_model = genai.GenerativeModel(grading_model)
            eval_response = eval_model.generate_content(evaluation_prompt)
            import re
            json_match = re.search(r'\{.*\}', eval_response.text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                score = result.get('score', 70)
                feedback = result.get('feedback', 'Оценка завершена.')
            else:
                score = 70
                feedback = "Автоматическая оценка не удалась, но диалог сохранен."
        except Exception as e:
            logger.error(f"Error during AI evaluation: {e}")
            score = 0
            feedback = "Произошла ошибка при оценке."
            
        AiConversationSubmissionAnswer.objects.create(
            submission=submission,
            transcript=self.conversation_history,
            overall_score=score, 
            evaluation_details={}
        )
        
        submission.score = score
        submission.status = 'graded'
        submission.feedback = feedback
        submission.save()
        return submission

    async def _handle_gemini_disconnect(self, message=None):
        self.gemini_ready = False
        self.not_ready_notified = False
        if message:
            try:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': message
                }))
            except Exception as err:
                logger.warning(f"Failed to notify client about Gemini disconnect: {err}")

    async def _ensure_gemini_ready(self):
        if self.gemini_ws and not self.gemini_ws.closed and self.gemini_ready:
            return True

        if not self.not_ready_notified:
            self.not_ready_notified = True
            try:
                await self.send(text_data=json.dumps({
                    'type': 'not_ready',
                    'message': 'Сенсей ещё подключается, попробуйте начать разговор через секунду.'
                }))
            except Exception as err:
                logger.warning(f"Failed to send not_ready notice: {err}")
        return False
