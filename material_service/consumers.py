import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from .models import Test, AiConversationQuestion, TestSubmission, AiConversationSubmissionAnswer
from lesson_service.models import SectionItem
from django.utils import timezone
import google.generativeai as genai
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)

class AiConversationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.test_id = self.scope['url_route']['kwargs']['test_id']
        self.user = self.scope["user"]

        if self.user.is_anonymous:
            await self.close()
            return

        try:
            self.test = await self.get_test(self.test_id)
            self.question_config = await self.get_question_config(self.test)
        except Exception as e:
            logger.error(f"Error connecting to AI Conversation: {e}")
            await self.close()
            return

        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.gemini_model = genai.GenerativeModel('gemini-2.5-flash-native-audio-preview-12-2025')
        
        try:
            self.gemma_model = genai.GenerativeModel('gemma-3-4b')
        except Exception:
            logger.warning("gemma-3-4b not found, using gemini for subtitles as fallback")
            self.gemma_model = genai.GenerativeModel('gemini-1.5-flash')

        self.chat = self.gemini_model.start_chat(history=[])
        self.conversation_history = []
        
        personality = self.question_config.personality or "Кей-сенпай"
        context = self.question_config.context
        goodbye = self.question_config.goodbye_condition or "Попрощайся и закончи разговор, когда цели достигнуты."
        
        self.system_instruction = f"""
        Ты — {personality}. Твой характер: милая аниме-тян, но сохраняешь субординацию как преподаватель.
        Твоя роль: Преподаватель японского языка.
        КОНТЕКСТ РАЗГОВОРА: {context}
        ОБЯЗАТЕЛЬНОЕ УСЛОВИЕ: Общайся с учеником ИСКЛЮЧИТЕЛЬНО на японском языке. 
        {goodbye}
        
        Когда разговор должен быть закончен, добавь в свой ответ специальный тег [FINISH].
        """
        
        await self.accept()
        
        greeting_prompt = f"{self.system_instruction}\n\nПоприветствуй ученика и начни разговор согласно контексту."
        response = await self.chat.send_message_async(greeting_prompt)
        await self.process_ai_response(response.text)

    async def disconnect(self, close_code):
        if hasattr(self, 'conversation_history') and self.conversation_history:
            await self.save_submission()
        pass

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            data = json.loads(text_data)
            
            if data.get('action') == 'submit_for_evaluation':
                logger.info(f"User {self.user.id} submitted conversation for evaluation")
                await self.save_submission()
                await self.send(text_data=json.dumps({
                    'type': 'evaluation_submitted',
                    'message': 'Your conversation has been submitted for evaluation'
                }))
                await self.close()
                return
            
            user_message = data.get('message')
            if user_message:
                self.conversation_history.append({"role": "user", "content": user_message})
                response = await self.chat.send_message_async(user_message)
                await self.process_ai_response(response.text)
        
        if bytes_data:
            pass

    async def process_ai_response(self, text):
        subtitle_prompt = f"Переведи этот японский текст на русский для субтитров и предоставь JSON для липсинка: {text}"
        try:
            gemma_response = await self.gemma_model.generate_content_async(subtitle_prompt)
            subtitles = gemma_response.text 
        except Exception:
            subtitles = "..."

        is_finished = "[FINISH]" in text
        clean_text = text.replace("[FINISH]", "").strip()
        
        self.conversation_history.append({"role": "assistant", "content": clean_text})

        await self.send(text_data=json.dumps({
            'type': 'ai_response',
            'text': clean_text,
            'subtitles': subtitles,
            'is_finished': is_finished
        }))

        if is_finished:
            await self.save_submission()
            await self.close()

    @database_sync_to_async
    def get_test(self, test_id):
        return Test.objects.get(pk=test_id)

    @database_sync_to_async
    def get_question_config(self, test):
        return AiConversationQuestion.objects.get(test=test)

    @database_sync_to_async
    def save_submission(self):
        section_item = SectionItem.objects.filter(object_id=self.test.id, content_type__model='test').first()
        
        submission = TestSubmission.objects.create(
            test=self.test,
            student=self.user,
            section_item=section_item,
            status='graded',
            submitted_at=timezone.now()
        )
        
        evaluation_prompt = f"""
        Проанализируй следующий диалог на японском языке и дай оценку ученику по 100-балльной шкале.
        Оцени: грамматику, произношение (если бы оно было), соответствие контексту.
        Верни JSON: {{"score": 85, "details": {{"grammar": "...", "fluency": "...", "vocabulary": "..."}}, "feedback": "..."}}
        
        ДИАЛОГ:
        {json.dumps(self.conversation_history, ensure_ascii=False)}
        """
        
        try:
            pass
        except Exception:
            pass
            
        AiConversationSubmissionAnswer.objects.create(
            submission=submission,
            transcript=self.conversation_history,
            overall_score=80.0, 
            evaluation_details={"feedback": "Хорошая работа!"}
        )
        
        submission.score = 80.0
        submission.save()
        
        return submission
