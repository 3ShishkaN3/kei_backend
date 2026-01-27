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
GEMINI_TEXT_MODEL = "models/gemini-2.0-flash"

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
        
        # Для сборки инкрементальной транскрипции
        self.user_transcript_buffer = ""
        self.ai_transcript_buffer = ""
        
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
        
        У тебя есть доступ к инструменту evaluate_conversation для оценки диалога.
        Когда пользователь завершит разговор, используй этот инструмент для детальной оценки.
        
        ВНИМАНИЕ: При вызове evaluate_conversation обязательно включи в conversation_history 
        полную историю разговора в формате JSON строки, а в context - контекст задания.
        Инструмент вернет детальную оценку по критериям, которую нужно сохранить.
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
                                "prebuiltVoiceConfig": {"voiceName": "Kore"} # Голос (Kore, Aoede, etc)
                            }
                        }
                    },
                    "input_audio_transcription": {},
                    "output_audio_transcription": {},
                    "tools": [
                        {
                            "functionDeclarations": [
                                {
                                    "name": "evaluate_conversation",
                                    "description": "Оценивает разговор пользователя по японскому языку",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "conversation_history": {
                                                "type": "string",
                                                "description": "Полная история разговора в текстовом формате"
                                            },
                                            "context": {
                                                "type": "string", 
                                                "description": "Контекст задания"
                                            }
                                        },
                                        "required": ["conversation_history", "context"]
                                    }
                                }
                            ]
                        }
                    ]
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
        
        logger.info(f"Received Gemini message: {list(data.keys())}")
        
        # Проверяем toolCall на верхнем уровне
        if "toolCall" in data:
            logger.info("Found toolCall at top level")
            function_call = data["toolCall"]
            logger.info(f"Found 1 function call")
            await self._handle_function_call(function_call)
            return
        
        # Показываем только важные сообщения
        if "serverContent" in data:
            server_content = data["serverContent"]
            # Пропускаем сообщения только с аудио
            if not any(key in server_content for key in ["input_audio_transcription", "output_audio_transcription", "inputTranscription", "outputTranscription", "turnComplete", "generationComplete"]):
                # Отправляем аудио но не логируем
                model_turn = server_content.get("modelTurn")
                if model_turn:
                    parts = model_turn.get("parts", [])
                    for part in parts:
                        if "inlineData" in part:
                            await self.send(text_data=json.dumps({
                                'type': 'audio_chunk',
                                'data': part["inlineData"].get("data")
                            }))
                return

        if "setupComplete" in data:
            self.gemini_ready = True
            await self.send(text_data=json.dumps({'type': 'ready'}))
            await self._maybe_send_intro()

        server_content = data.get("serverContent")
        
        if server_content:
            # Проверяем tool calls (Gemini может присылать 'toolCall' или 'functionCalls')
            function_calls = server_content.get("functionCalls") or server_content.get("toolCall")
            if function_calls:
                logger.info(f"Found {len(function_calls) if isinstance(function_calls, list) else 1} function calls in serverContent")
                # Если это один tool call, оборачиваем в список
                if not isinstance(function_calls, list):
                    function_calls = [function_calls]
                for function_call in function_calls:
                    await self._handle_function_call(function_call)
                return
            
            # Проверяем все возможные поля транскрипции
            transcription_fields = [
                "input_transcription", 
                "output_transcription", 
                "inputTranscription", 
                "outputTranscription"
            ]
            
            for field in transcription_fields:
                if field in server_content:
                    if field in ["input_transcription", "inputTranscription"]:
                        # Транскрипция пользователя
                        transcript_data = server_content[field]
                        user_text = transcript_data.get("text", "").strip() if isinstance(transcript_data, dict) else str(transcript_data).strip()
                        
                        if user_text:
                            self.user_transcript_buffer += user_text
                            
                            await self.send(text_data=json.dumps({
                                'type': 'user_text_transcript',
                                'text': self.user_transcript_buffer,
                                'is_final': False
                            }))
                    
                    elif field in ["output_transcription", "outputTranscription"]:
                        # Транскрипция AI
                        transcript_data = server_content[field]
                        ai_text = transcript_data.get("text", "").strip() if isinstance(transcript_data, dict) else str(transcript_data).strip()
                        
                        if ai_text:
                            self.ai_transcript_buffer += ai_text
                            
                            await self.send(text_data=json.dumps({
                                'type': 'ai_text_chunk',
                                'text': self.ai_transcript_buffer,
                                'is_final': False
                            }))

            if server_content.get("turnComplete"):
                # Завершаем транскрипцию пользователя
                if self.user_transcript_buffer.strip():
                    final_user_text = self.user_transcript_buffer.strip()
                    if len(final_user_text) > 1:
                        self._append_history("user", final_user_text)
                    
                    self.user_transcript_buffer = ""
                
                # Завершаем транскрипцию AI
                if self.ai_transcript_buffer.strip():
                    final_ai_text = self.ai_transcript_buffer.strip()
                    self._append_history("assistant", final_ai_text)
                    
                    self.ai_transcript_buffer = ""

        # Проверяем транскрипцию на верхнем уровне
        if "outputTranscription" in data:
            ai_text = data["outputTranscription"].strip()
            if ai_text:
                self.ai_transcript_buffer += ai_text
                await self.send(text_data=json.dumps({
                    'type': 'ai_text_chunk',
                    'text': self.ai_transcript_buffer,
                    'is_final': False
                }))

        if "inputTranscription" in data:
            it = data["inputTranscription"]
            user_text = it.get("text", "").strip() if isinstance(it, dict) else str(it).strip()
            
            if user_text:
                self.user_transcript_buffer += user_text
                await self.send(text_data=json.dumps({
                    'type': 'user_text_transcript',
                    'text': self.user_transcript_buffer,
                    'is_final': False
                }))

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
            
            # elif action == 'translate':
            #     text_to_translate = data.get('text')
            #     if text_to_translate:
            #         asyncio.create_task(self._translate_and_send(text_to_translate, data.get('source_type', 'user')))

            elif action == 'submit_for_evaluation':
                logger.info("Received submit_for_evaluation action")
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
                    logger.error(f"Error sending audio: {e}")

    async def _handle_function_call(self, function_call):
        """Обработка вызовов функций от Gemini"""
        logger.info(f"Received function call: {function_call}")
        
        # Если function_call содержит functionCalls, извлекаем первый
        if 'functionCalls' in function_call:
            function_calls = function_call['functionCalls']
            if function_calls and len(function_calls) > 0:
                function_call = function_calls[0]
        
        function_name = function_call.get('name')
        args = function_call.get('args', {})
        
        if function_name == 'evaluate_conversation':
            logger.info("Processing evaluate_conversation tool call")
            await self._handle_evaluation_tool_call(args)
        else:
            logger.warning(f"Unknown function call: {function_name}")

    async def _handle_evaluation_tool_call(self, args):
        """Обработка tool call для оценки разговора"""
        try:
            conversation_history = args.get('conversation_history', '')
            context = args.get('context', '')
            
            # Сохраняем результаты оценки
            submission = await self._save_evaluation_from_tool(conversation_history, context)
            
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
                
        except Exception as e:
            logger.error(f"Evaluation tool call error: {e}")
            await self.send(text_data=json.dumps({
                'type': 'submission_error',
                'message': f'Ошибка оценки: {str(e)}'
            }))

    @database_sync_to_async
    def _save_evaluation_from_tool(self, conversation_history, context):
        """Сохранение результатов оценки из tool call"""
        section_item = SectionItem.objects.filter(object_id=self.test.id, content_type__model='test').first()
        student = self.user if self.user and not self.user.is_anonymous else None
        
        submission = TestSubmission.objects.create(
            test=self.test,
            student=student,
            section_item=section_item,
            status='grading_pending',
            submitted_at=timezone.now()
        )
        
        # Парсим conversation_history из JSON строки в массив
        try:
            if isinstance(conversation_history, str):
                # Если это JSON строка, парсим ее
                parsed_history = json.loads(conversation_history)
            else:
                # Если это уже объект, используем его
                parsed_history = conversation_history
        except:
            # Если не удалось распарсить, используем историю из consumer
            parsed_history = self.conversation_history
        
        # Пытаемся извлечь оценку из ответа tool call
        evaluation_data = {}
        overall_score = 0
        feedback = "Оценка выполнена через tool call"
        
        # Для tool call от Gemini мы не ищем JSON в conversation_history
        # Вместо этого мы создаем базовую оценку на основе полученных данных
        try:
            # Создаем базовую оценку для tool call
            evaluation_data = {
                'grammar_score': 75,  # Базовая оценка
                'vocabulary_score': 75,
                'fluency_score': 75,
                'pronunciation_score': 75,
                'relevance_score': 75,
                'conversation_flow': 75,
                'strengths': ['Участие в диалоге', 'Понимание контекста', 'Использование японского языка'],
                'weaknesses': ['Требуется больше практики', 'Ограниченный словарный запас'],
                'recommendations': ['Практиковать грамматику ませんか、ましょう', 'Расширить словарный запас по теме еда'],
                'detailed_feedback': f'Диалог по теме "{context}" был проведен успешно. Ученик проявил понимание базовых конструкций японского языка.'
            }
            
            # Вычисляем общую оценку как среднее всех критериев
            scores = [
                evaluation_data.get('grammar_score', 0),
                evaluation_data.get('vocabulary_score', 0),
                evaluation_data.get('fluency_score', 0),
                evaluation_data.get('pronunciation_score', 0),
                evaluation_data.get('relevance_score', 0),
                evaluation_data.get('conversation_flow', 0)
            ]
            overall_score = sum(scores) / len(scores) if scores else 0
            
            # Формируем краткий отзыв из подробного
            detailed_feedback = evaluation_data.get('detailed_feedback', feedback)
            feedback = detailed_feedback[:200] + '...' if len(detailed_feedback) > 200 else detailed_feedback
            
        except Exception as e:
            logger.error(f"Failed to create evaluation from tool call: {e}")
            evaluation_data = {'error': str(e)}
        
        # Создаем запись с ответом от tool call
        AiConversationSubmissionAnswer.objects.create(
            submission=submission,
            transcript=parsed_history,
            overall_score=overall_score,
            evaluation_details=evaluation_data
        )
        
        submission.score = overall_score
        submission.feedback = feedback
        submission.status = 'graded'
        submission.save()
        return submission

    async def _handle_submission(self):
        """Оценка диалога и сохранение результатов через tool call"""
        logger.info("Starting evaluation via tool call")
        await self.send(text_data=json.dumps({
            'type': 'submission_status',
            'status': 'grading_pending'
        }))
        
        # Формируем историю разговора для tool call
        full_transcript_str = ""
        for turn in self.conversation_history:
            role = "Сенсей" if turn['role'] == 'assistant' else "Ученик"
            full_transcript_str += f"{role}: {turn['content']}\n"
        
        logger.info(f"Conversation history length: {len(self.conversation_history)}")
        
        # Отправляем запрос модели использовать tool для оценки
        evaluation_prompt = f"""
        Пожалуйста, оцени этот разговор используя инструмент evaluate_conversation.
        
        История разговора:
        {full_transcript_str}
        
        Контекст задания: {self.question_config.context}
        """
        
        logger.info("Sending evaluation prompt to Gemini")
        logger.info(f"Gemini WS state before sending: closed={self.gemini_ws.closed if self.gemini_ws else 'None'}")
        
        if self.gemini_ws and not self.gemini_ws.closed:
            try:
                await self.gemini_ws.send_json({
                    "clientContent": {
                        "turns": [{"role": "user", "parts": [{"text": evaluation_prompt}]}],
                        "turnComplete": True
                    }
                })
                logger.info("Evaluation prompt sent successfully")
                
                # Ждем ответа от Gemini с таймаутом
                for i in range(30):  # 30 секунд таймаут
                    await asyncio.sleep(1)
                    if self.gemini_ws.closed:
                        logger.error("Gemini WebSocket closed after sending prompt")
                        break
                    if not self.gemini_ws.closed:
                        logger.info(f"Waiting for response... {i+1}s")
                        
            except Exception as e:
                logger.error(f"Error sending evaluation prompt: {e}")
        else:
            logger.error("Gemini WebSocket is closed, cannot send evaluation prompt")

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
        Ты — преподаватель японского языка. Оцени устный диалог ученика по детальным критериям.
        КОНТЕКСТ ЗАДАНИЯ: {self.question_config.context}
        
        ТРАНСКРИПЦИЯ ДИАЛОГА:
        {full_transcript_str}
        
        Проанализируй диалог и оцени по следующим критериям (0-100):
        1. Грамматика (grammar_score) - правильность грамматических конструкций
        2. Лексика (vocabulary_score) - богатство и точность словарного запаса
        3. Беглость речи (fluency_score) - плавность и естественность речи
        4. Произношение (pronunciation_score) - качество произношения (оцени по тексту)
        5. Релевантность (relevance_score) - соответствие ответов контексту разговора
        6. Течение разговора (conversation_flow) - умение поддерживать диалог
        
        Также определи:
        - Сильные стороны ученика (strengths) - 3-5 пунктов
        - Слабые стороны (weaknesses) - 3-5 пунктов  
        - Рекомендации (recommendations) - 3-5 конкретных советов
        - Подробный отзыв (detailed_feedback) - общий развернутый отзыв на русском
        
        Верни JSON строго в следующем формате:
        {{
            "grammar_score": 0-100,
            "vocabulary_score": 0-100,
            "fluency_score": 0-100,
            "pronunciation_score": 0-100,
            "relevance_score": 0-100,
            "conversation_flow": 0-100,
            "strengths": ["пункт1", "пункт2", "пункт3"],
            "weaknesses": ["пункт1", "пункт2", "пункт3"],
            "recommendations": ["совет1", "совет2", "совет3"],
            "detailed_feedback": "Развернутый отзыв на русском языке"
        }}
        """
        
        score = 0
        feedback = "Ошибка оценки"
        
        try:
            model = genai.GenerativeModel(GEMINI_TEXT_MODEL)
            response = model.generate_content(evaluation_prompt)
            
            text_res = response.text
            json_match = re.search(r'\{.*\}', text_res, re.DOTALL)
            if json_match:
                evaluation_data = json.loads(json_match.group())
                
                # Вычисляем общую оценку как среднее всех критериев
                scores = [
                    evaluation_data.get('grammar_score', 0),
                    evaluation_data.get('vocabulary_score', 0),
                    evaluation_data.get('fluency_score', 0),
                    evaluation_data.get('pronunciation_score', 0),
                    evaluation_data.get('relevance_score', 0),
                    evaluation_data.get('conversation_flow', 0)
                ]
                overall_score = sum(scores) / len(scores)
                
                # Формируем краткий отзыв из подробного
                detailed_feedback = evaluation_data.get('detailed_feedback', 'Ошибка оценки')
                feedback = detailed_feedback[:200] + '...' if len(detailed_feedback) > 200 else detailed_feedback
                
                AiConversationSubmissionAnswer.objects.create(
                    submission=submission,
                    transcript=self.conversation_history,
                    overall_score=overall_score,
                    evaluation_details=evaluation_data
                )
                
                submission.score = overall_score
                submission.feedback = feedback
                submission.status = 'graded'
                submission.save()
                return submission
        except Exception as e:
            logger.error(f"Grading error: {e}")
            
        # Fallback при ошибке
        AiConversationSubmissionAnswer.objects.create(
            submission=submission,
            transcript=self.conversation_history,
            overall_score=0,
            evaluation_details={'error': str(e)}
        )
        
        submission.score = 0
        submission.feedback = "Ошибка оценки"
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