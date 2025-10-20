import google.generativeai as genai
import json
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class LLMGradingService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model_name = settings.LLM_GRADING_MODEL
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY не найден в настройках.")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)

    def grade_answer(self, task_text, student_answer, correct_answer):
        """
        Оценивает ответ студента, сравнивая его с правильным ответом.
        Возвращает словарь с оценкой и комментарием.
        """
        prompt = self._build_prompt(task_text, student_answer, correct_answer)
        
        try:
            response = self.model.generate_content(prompt)
            # Попытка распарсить JSON из ответа
            # Gemini может возвращать JSON в тройных обратных кавычках с префиксом json
            cleaned_response = response.text.strip().replace('```json', '').replace('```', '')
            result = json.loads(cleaned_response)
            
            # Валидация результата
            if 'is_correct' not in result or 'score' not in result:
                raise ValueError("Ответ LLM не содержит обязательных полей 'is_correct' и 'score'.")

            return {
                'is_correct': bool(result.get('is_correct', False)),
                'score': float(result.get('score', 0.0)),
                'feedback': result.get('feedback', 'Не удалось сгенерировать комментарий.')
            }

        except Exception as e:
            logger.error(f"Ошибка при взаимодействии с LLM API: {e}")
            return {
                'is_correct': False,
                'score': 0.0,
                'feedback': f"Системная ошибка при проверке ответа: {e}"
            }

    def _build_prompt(self, task_text, student_answer, correct_answer):
        return f"""
        Ты — дружелюбный ассистент преподавателя, который помогает проверять ответы студентов.
        Твоя задача — сравнить ответ студента с ответом преподавателя и определить, является ли он правильным.
        Ответ должен быть в формате JSON.

        ЗАДАНИЕ: "{task_text}"
        ОТВЕТ ПРЕПОДАВАТЕЛЯ: "{correct_answer}"
        ОТВЕТ СТУДЕНТА: "{student_answer}"

        Проанализируй ответ студента. Учти, что студент может использовать синонимы, немного другую формулировку или порядок слов, но суть ответа должна совпадать с ответом преподавателя.

        Верни JSON-объект со следующей структурой:
        {{
          "is_correct": true/false,       // true, если ответ полностью или в основном верный.
          "is_partially_correct": true/false, // true, если ответ частично верный, но не полный.
          "score": 100/50/20,             // 100 за верный ответ, 50 за частично верный, 20 за неверную попытку.
          "feedback": "<Твой комментарий>"  // Краткий комментарий для студента.
        }}
        Например, если студент забыл одно слово, но в целом ответил правильно, это частично верный ответ: is_correct: false, is_partially_correct: true, score: 50.
        """
