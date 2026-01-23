import json
import logging
import re
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

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GEMINI_API_KEY)

GEMINI_WS_URL = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={settings.GEMINI_API_KEY}"
GEMINI_NATIVE_AUDIO_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
GEMINI_TEXT_MODEL = "models/gemini-2.5-flash"

class AiConversationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.test_id = self.scope['url_route']['kwargs']['test_id']
        self.user = self.scope.get("user")

        logger.info(f"Connecting AI Conversation. User: {self.user}")
        
        if not self.user or self.user.is_anonymous:
            if not settings.DEBUG:
                await self.close()
                return
            logger.info("Allowing anonymous connection (DEBUG mode)")

        try:
            self.test = await self.get_test(self.test_id)
            self.question_config = await self.get_question_config(self.test)
        except Exception as e:
            logger.error(f"Error loading test config: {e}")
            await self.close()
            return

        self.conversation_history = [] # Полная история для оценки
        self.gemini_ws = None
        self.gemini_session = None
        self.receiver_task = None
        self.gemini_ready = False
        
        self.intro_sent = False
        self.start_requested = False
        
        personality = self.question_config.personality or "Кей-сенпай"
        context = self.question_config.context
        goodbye = self.question_config.goodbye_condition or "Попрощайся и закончи разговор."
        
        self.system_instruction = f"""
        Ты — {personality}. Твой характер: аниме-тян, преподаватель японского языка.
        ОБЯЗАТЕЛЬНОЕ УСЛОВИЕ: Твои ответы должны быть СТРОГО на японском языке. 
        Не используй русский или английский в аудио-ответах, только японский.
        КОНТЕКСТ РАЗГОВОРА: {context}
        КОНЕЦ ДИАЛОГА: {goodbye}
        """
        
        await self.accept()
        await self.init_gemini_live()

    async def init_gemini_live(self):
        """Устанавливает WebSocket соединение с Google Gemini"""
        try:
            logger.info(f"Connecting to Gemini: {GEMINI_WS_URL}")
            
            timeout = aiohttp.ClientTimeout(total=60)
            self.gemini_session = aiohttp.ClientSession(timeout=timeout)
            
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            self.gemini_ws = await self.gemini_session.ws_connect(GEMINI_WS_URL, ssl=ssl_context)
            
            setup_msg = {
                "setup": {
                    "model": GEMINI_NATIVE_AUDIO_MODEL,
                    "systemInstruction": {
                        "parts": [{"text": self.system_instruction}]
                    },
                    "generationConfig": {
                        "responseModalities": ["AUDIO"], # Модель отвечает аудио
                        "speechConfig": {
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {"voiceName": "Aoede"} # Голос (Kore, Aoede, etc)
                            }
                        }
                    }
                }
            } # Что за хуйня вообще эта структура? Никто не объяснил
            await self.gemini_ws.send_json(setup_msg)
            
            self.receiver_task = asyncio.create_task(self.receive_from_gemini())
            logger.info("Gemini Live initialized.")
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini Live: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Ошибка подключения к ИИ-сервису.'
            }))

    async def receive_from_gemini(self):
        """Главный цикл чтения сообщений от Gemini.
        
            Честно говоря, тут жесть какая-то происходит. 
            Надо разобраться.
            Я просто скопировал код из документации Gemini.
            Я в шоке, что это вообще работает."""
        try:
            async for msg in self.gemini_ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_gemini_message(json.loads(msg.data))
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    try:
                        decoded = msg.data.decode('utf-8')
                        await self._handle_gemini_message(json.loads(decoded))
                    except Exception:
                        pass
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    logger.warning("Gemini connection closed/error.")
                    break
        except Exception as e:
            logger.error(f"Error receiving from Gemini: {e}")
        finally:
            self.gemini_ready = False

    async def _handle_gemini_message(self, data):
        """Разбор сообщения от Gemini и отправка на фронтенд"""
        if not data: return

        if "setupComplete" in data:
            self.gemini_ready = True
            await self.send(text_data=json.dumps({'type': 'ready'}))
            await self._maybe_send_intro()
            return

        server_content = data.get("serverContent")
        
        if server_content:
            model_turn = server_content.get("modelTurn")
            if model_turn:
                parts = model_turn.get("parts", [])
                for part in parts:
                    if "inlineData" in part:
                        await self.send(text_data=json.dumps({
                            'type': 'audio_chunk',
                            'data': part["inlineData"].get("data")
                        }))

            if server_content.get("turnComplete"):
                await self.send(text_data=json.dumps({'type': 'turn_complete'}))

        if "outputTranscription" in data:
            # Текст на японском
            ai_text = data["outputTranscription"].strip()
            if ai_text:
                self._append_history("assistant", ai_text)

                await self.send(text_data=json.dumps({
                    'type': 'ai_text_chunk',
                    'text': ai_text
                }))
                
                asyncio.create_task(self._translate_and_send(ai_text, "ai"))

        if "inputTranscription" in data:
            it = data["inputTranscription"]
            user_text = it.get("text", "") if isinstance(it, dict) else it
            
            is_final = True 
            if isinstance(it, dict):
                pass

            if user_text:
                await self.send(text_data=json.dumps({
                    'type': 'user_text_transcript',
                    'text': user_text,
                    'is_final': True
                }))
                
                if len(user_text.strip()) > 1:
                    self._append_history("user", user_text)
                    asyncio.create_task(self._translate_and_send(user_text, "user"))

    async def _translate_and_send(self, text, source_type):
        """
        Отдельная задача для перевода текста.
        source_type: 'ai' или 'user'
        """
        if not text or len(text.strip()) < 1:
            return

        try:
            model = genai.GenerativeModel(GEMINI_TEXT_MODEL)
            
            prompt = f"""
            Ты — переводчик субтитров. 
            Переведи следующий текст с японского на русский язык.
            
            Текст: "{text}"
            
            Требования:
            1. Только русский перевод.
            2. Естественный разговорный стиль.
            3. Никаких пояснений, только текст.
            """
            
            response = await model.generate_content_async(prompt)
            translated_text = response.text.strip()
            
            translated_text = re.sub(r'^["\']|["\']$', '', translated_text)

            msg_type = 'ai_text_translated' if source_type == 'ai' else 'user_text_translated'
            
            await self.send(text_data=json.dumps({
                'type': msg_type,
                'text': text,         # Оригинал (ключ для матчинга на фронте)
                'translated': translated_text
            }))

        except Exception as e:
            logger.warning(f"Translation failed for '{text}': {e}")
            pass

    async def receive(self, text_data=None, bytes_data=None):
        """Обработка сообщений от браузера (клиента)"""
        
        if text_data:
            data = json.loads(text_data)
            action = data.get('action')

            if action == 'start':
                self.start_requested = True
                await self._maybe_send_intro()
            
            elif action == 'submit_for_evaluation':
                await self._handle_submission()

            elif action == 'chat':
                message = data.get('message')
                if message and self.gemini_ws:
                    payload = {
                        "clientContent": {
                            "turns": [{"role": "user", "parts": [{"text": message}]}],
                            "turnComplete": True
                        }
                    }
                    await self.gemini_ws.send_json(payload)
                    self._append_history("user", message)
                    asyncio.create_task(self._translate_and_send(message, "user"))

        if bytes_data:
            if self.gemini_ws and not self.gemini_ws.closed:
                try:
                    import base64
                    # Gemini требует base64 в JSON, даже если socket поддерживает binary
                    # Google - корпорация зла
                    b64_data = base64.b64encode(bytes_data).decode('utf-8')
                    await self.gemini_ws.send_json({
                        "realtimeInput": {
                            "mediaChunks": [{
                                "data": b64_data,
                                "mimeType": "audio/pcm;rate=16000"
                            }]
                        }
                    }) # Нет, я серьёзно. Они даже не могут внятную документацию написать
                    # И это только начало
                except Exception as e:
                    logger.error(f"Error sending audio: {e}")

    async def _handle_submission(self):
        """Оценка диалога и сохранение результатов"""
        await self.send(text_data=json.dumps({
            'type': 'submission_status',
            'status': 'grading_pending'
        }))

        submission = await self.save_submission()

        if submission:
            submission_payload = {
                'id': submission.id,
                'score': submission.score,
                'feedback': submission.feedback,
                'status': submission.status
            }
            await self.send(text_data=json.dumps({
                'type': 'submission_update',
                'submission': submission_payload
            }))
        else:
            await self.send(text_data=json.dumps({
                'type': 'submission_error',
                'message': 'Ошибка сохранения результатов.'
            }))
        
        await self.close()

    @database_sync_to_async
    def save_submission(self):
        """Логика сохранения в БД и вызова LLM для оценки"""
        section_item = SectionItem.objects.filter(object_id=self.test.id, content_type__model='test').first()
        student = self.user if self.user and not self.user.is_anonymous else None
        
        submission = TestSubmission.objects.create(
            test=self.test,
            student=student,
            section_item=section_item,
            status='grading_pending',
            submitted_at=timezone.now()
        )
        
        full_transcript_str = ""
        for turn in self.conversation_history:
            role = "Сенсей" if turn['role'] == 'assistant' else "Ученик"
            full_transcript_str += f"{role}: {turn['content']}\n"

        evaluation_prompt = f"""
        Ты — преподаватель японского. Оцени устный диалог ученика.
        КОНТЕКСТ ЗАДАНИЯ: {self.question_config.context}
        
        ТРАНСКРИПЦИЯ ДИАЛОГА:
        {full_transcript_str}
        
        Критерии: грамматика, лексика, адекватность ответов.
        Игнорируй ошибки распознавания речи, оценивай суть.
        
        Верни JSON: {{ "score": (0-100), "feedback": "Текст отзыва на русском" }}
        """
        
        score = 0
        feedback = "Ошибка оценки"
        
        try:
            model = genai.GenerativeModel(GEMINI_TEXT_MODEL)
            response = model.generate_content(evaluation_prompt)
            
            text_res = response.text
            json_match = re.search(r'\{.*\}', text_res, re.DOTALL)
            if json_match:
                res_data = json.loads(json_match.group())
                score = res_data.get('score', 0)
                feedback = res_data.get('feedback', '')
        except Exception as e:
            logger.error(f"Grading error: {e}")

        AiConversationSubmissionAnswer.objects.create(
            submission=submission,
            transcript=self.conversation_history,
            overall_score=score,
            evaluation_details={'full_log': self.conversation_history}
        )
        
        submission.score = score
        submission.feedback = feedback
        submission.status = 'graded'
        submission.save()
        return submission

    async def _maybe_send_intro(self):
        """Отправляет скрытую команду модели начать разговор"""
        if self.intro_sent or not self.start_requested or not self.gemini_ready:
            return

        intro_prompt = "Поприветствуй студента и начни ролевую игру согласно контексту. Кратко."
        try:
            await self.gemini_ws.send_json({
                "clientContent": {
                    "turns": [{"role": "user", "parts": [{"text": intro_prompt}]}],
                    "turnComplete": True
                }
            })
            self.intro_sent = True
        except Exception as e:
            logger.error(f"Intro send error: {e}")

    def _append_history(self, role, content):
        """Добавляет запись в историю, склеивая, если роль повторяется подряд"""
        content = content.strip()
        if not content: return
        
        if self.conversation_history and self.conversation_history[-1]["role"] == role:
            self.conversation_history[-1]["content"] += " " + content
        else:
            self.conversation_history.append({"role": role, "content": content})

    async def disconnect(self, close_code):
        if self.receiver_task:
            self.receiver_task.cancel()
        if self.gemini_ws:
            await self.gemini_ws.close()
        if self.gemini_session:
            await self.gemini_session.close()
        logger.info(f"AI Conversation Disconnected: {close_code}")

    @database_sync_to_async
    def get_test(self, test_id):
        return Test.objects.get(pk=test_id)

    @database_sync_to_async
    def get_question_config(self, test):
        return AiConversationQuestion.objects.get(test=test)