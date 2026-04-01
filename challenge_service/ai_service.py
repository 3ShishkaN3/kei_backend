import google.generativeai as genai
import json
import logging
import re
from django.conf import settings

logger = logging.getLogger(__name__)

KNOWLEDGE_PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Сильные стороны ученика"
        },
        "weaknesses": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Слабые стороны, темы для повторения"
        },
        "recommended_topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Рекомендованные темы для тренировки"
        },
        "difficulty_level": {
            "type": "string",
            "description": "Оценённый уровень ученика"
        },
        "summary": {
            "type": "string",
            "description": "Краткое текстовое резюме о знаниях ученика"
        }
    },
    "required": ["strengths", "weaknesses", "recommended_topics", "difficulty_level", "summary"]
}

class ChallengeAIService:
    """Сервис генерации ежедневных испытаний через Gemini API."""

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model_name = settings.CHALLENGE_AI_MODEL
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY не найден в настройках.")
        genai.configure(api_key=self.api_key)

    def _get_model(self, response_schema=None, tools=None):
        """Создаёт модель с опциональным structured output или tool calls."""
        generation_config = {
            "temperature": 0.8,
            "top_p": 0.95,
            "max_output_tokens": 16384,
        }
        if response_schema:
            generation_config["response_mime_type"] = "application/json"
            generation_config["response_schema"] = response_schema

        return genai.GenerativeModel(
            self.model_name,
            generation_config=generation_config,
            tools=tools
        )

    def analyze_user_profile(self, user, course, existing_profile=None):
        """
        Анализирует прогресс ученика и создаёт/обновляет профиль знаний.
        Если existing_profile передан — инкрементальный анализ (только новые данные).
        """
        from progress_service.models import TestProgress
        from material_service.models import TestSubmission
        from django.utils import timezone

        last_analyzed = None
        if existing_profile and existing_profile.last_analyzed_at:
            last_analyzed = existing_profile.last_analyzed_at

        submissions_qs = TestSubmission.objects.filter(
            student=user,
            section_item__section__lesson__course=course,
        ).select_related('test')

        if last_analyzed:
            submissions_qs = submissions_qs.filter(submitted_at__gt=last_analyzed)

        submissions = submissions_qs.order_by('-submitted_at')[:100]

        if not submissions.exists() and existing_profile and existing_profile.profile_data:
            return existing_profile.profile_data

        progress_data = []
        for sub in submissions:
            progress_data.append({
                'test_title': sub.test.title,
                'test_type': sub.test.test_type,
                'status': sub.status,
                'score': float(sub.score) if sub.score else 0,
                'feedback': sub.feedback[:200] if sub.feedback else '',
            })

        existing_summary = ''
        if existing_profile and existing_profile.profile_data:
            existing_summary = json.dumps(existing_profile.profile_data, ensure_ascii=False)

        prompt = self._build_profile_prompt(course.title, progress_data, existing_summary)
        model = self._get_model(response_schema=KNOWLEDGE_PROFILE_SCHEMA)

        try:
            response = model.generate_content(prompt)
            result = json.loads(response.text)
            return result
        except Exception as e:
            logger.error(f"Ошибка анализа профиля знаний: {e}")
            return {
                "strengths": [],
                "weaknesses": ["Недостаточно данных для анализа"],
                "recommended_topics": [],
                "difficulty_level": "beginner",
                "summary": "Профиль ещё не сформирован — недостаточно данных."
            }

    def generate_full_challenge_streamed(self, course, knowledge_profile):
        """
        Генерирует только основные задания в одном потоке
        через вызовы функций (Tool Calling).
        Yields events: {'type': 'item', 'data': dict}
        """
        items = self.generate_full_challenge_validated(course, knowledge_profile)
        for item in items:
            yield {"type": "item", "data": item}

    def _tools_add_challenge_item(self):
        return [
            {
                "function_declarations": [
                    {
                        "name": "add_challenge_item",
                        "description": "Добавляет одно основное задание",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "item_type": {
                                    "type": "string",
                                    "description": "Одно из: mcq-single, mcq-multi, word-order, drag-and-drop, free-text",
                                },
                                "title": {"type": "string"},
                                "question": {"type": "string"},
                                "options": {"type": "array", "items": {"type": "string"}},
                                "correct_answer": {"type": "string"},
                                "correct_answers": {"type": "array", "items": {"type": "string"}},
                                "correct_order": {"type": "array", "items": {"type": "string"}},
                                "drag_drop_pairs": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "prompt": {"type": "string"},
                                            "answer": {"type": "string"},
                                        },
                                    },
                                },
                                "explanation": {"type": "string"},
                            },
                            "required": ["item_type", "title", "question"],
                        },
                    }
                ]
            }
        ]

    def _normalize_text(self, value):
        if value is None:
            return ""
        text = str(value).strip().lower()
        text = re.sub(r"[。．、,!?！？:：;；\"'`«»()（）\[\]{}]", "", text)
        text = re.sub(r"[\s\u3000]+", "", text)
        return text

    def _validate_item(self, item):
        """
        Возвращает список ошибок. Пусто => валидно.
        Валидируем именно contract, который потом используется в _create_test_from_ai_item.
        """
        errors = []
        if not isinstance(item, dict):
            return ["item должен быть объектом"]

        item_type = item.get("item_type")
        title = (item.get("title") or "").strip()
        question = (item.get("question") or "").strip()
        explanation = (item.get("explanation") or "").strip()

        if item_type not in ("mcq-single", "mcq-multi", "word-order", "drag-and-drop", "free-text"):
            errors.append("item_type должен быть одним из: mcq-single, mcq-multi, word-order, drag-and-drop, free-text")
        if not title:
            errors.append("title обязателен")
        if not question:
            errors.append("question обязателен")
        if not explanation:
            errors.append("explanation обязателен (нужно пояснение ответа)")

        if item_type in ("mcq-single", "mcq-multi"):
            options = item.get("options") or []
            if not isinstance(options, list) or len(options) < 3:
                errors.append("MCQ: options должен быть массивом из минимум 3 вариантов")
            else:
                cleaned = [str(o).strip() for o in options if str(o).strip()]
                if len(cleaned) < 3:
                    errors.append("MCQ: варианты ответа не должны быть пустыми")
            if item_type == "mcq-single":
                correct = (item.get("correct_answer") or "").strip()
                if not correct:
                    errors.append("MCQ single: correct_answer обязателен")
                else:
                    norm_correct = self._normalize_text(correct)
                    norm_opts = {self._normalize_text(o) for o in options}
                    if norm_correct and norm_correct not in norm_opts:
                        errors.append("MCQ single: correct_answer должен совпадать с одним из options")
            else:
                correct_answers = item.get("correct_answers") or []
                if not isinstance(correct_answers, list) or len(correct_answers) == 0:
                    errors.append("MCQ multi: correct_answers обязателен и должен быть непустым массивом")
                else:
                    norm_opts = {self._normalize_text(o) for o in options}
                    for ca in correct_answers:
                        if self._normalize_text(ca) not in norm_opts:
                            errors.append("MCQ multi: каждый correct_answers должен присутствовать в options")
                            break

        if item_type == "word-order":
            correct_order = item.get("correct_order") or []
            if not isinstance(correct_order, list) or len(correct_order) < 2:
                errors.append("word-order: correct_order должен быть массивом минимум из 2 элементов")
            else:
                if any(not str(w).strip() for w in correct_order):
                    errors.append("word-order: correct_order не должен содержать пустые элементы")

        if item_type == "drag-and-drop":
            pairs = item.get("pairs") or item.get("drag_drop_pairs") or []
            if not isinstance(pairs, list) or len(pairs) < 2:
                errors.append("drag-and-drop: pairs/drag_drop_pairs должен быть массивом минимум из 2 пар")
            else:
                for p in pairs:
                    if not isinstance(p, dict):
                        errors.append("drag-and-drop: каждая пара должна быть объектом {prompt, answer}")
                        break
                    if not str(p.get("prompt") or "").strip() or not str(p.get("answer") or "").strip():
                        errors.append("drag-and-drop: у каждой пары должны быть непустые prompt и answer")
                        break

        if item_type == "free-text":
            correct = (item.get("correct_answer") or "").strip()
            if not correct:
                errors.append("free-text: correct_answer обязателен")

        return errors

    def _extract_items_from_response(self, response, limit=15):
        items = []
        try:
            for cand in getattr(response, "candidates", []) or []:
                for part in getattr(cand.content, "parts", []) or []:
                    if getattr(part, "function_call", None):
                        part_dict = type(part).to_dict(part)
                        fn_call = part_dict.get("function_call", {})
                        if fn_call.get("name") != "add_challenge_item":
                            continue
                        args = fn_call.get("args", {}) or {}
                        if "drag_drop_pairs" in args and "pairs" not in args:
                            args["pairs"] = args.pop("drag_drop_pairs")
                        items.append(args)
                        if len(items) >= limit:
                            return items
        except Exception:
            pass
        return items[:limit]

    def _generate_items_once(self, course, knowledge_profile, count=15, extra_rules=""):
        profile_json = json.dumps(knowledge_profile, ensure_ascii=False)
        prompt = f"""Ты — ИИ-преподаватель японского. Базируясь на профиле знаний: {profile_json}

Сгенерируй ежедневное испытание для курса "{course.title}".
Нужно вернуть ровно {count} основных заданий через функцию `add_challenge_item`.

КРИТИЧЕСКИЕ ПРАВИЛА:
- Возвращай результат ТОЛЬКО через tool calls, без обычного текста.
- Используй типы: mcq-single, mcq-multi, word-order, drag-and-drop, free-text.
- Для каждого задания ОБЯЗАТЕЛЬНО заполни explanation (пояснение на русском).
- Для mcq-single: correct_answer должен ТОЧНО совпадать с одним из options.
- Для mcq-multi: каждый correct_answers должен ТОЧНО присутствовать в options.
- Для word-order: correct_order минимум 2 элемента.
- Для drag-and-drop: pairs минимум 2 пары {{prompt, answer}}.
- Для free-text: correct_answer не пустой.
{extra_rules}
"""

        model = self._get_model(tools=self._tools_add_challenge_item())
        response = model.generate_content(prompt, stream=False)
        return self._extract_items_from_response(response, limit=count)

    def _regenerate_single_item(self, course, knowledge_profile, desired_type, validation_errors, previous_item=None):
        profile_json = json.dumps(knowledge_profile, ensure_ascii=False)
        prev_json = json.dumps(previous_item or {}, ensure_ascii=False)
        errors_text = "\n".join([f"- {e}" for e in validation_errors])
        prompt = f"""Ты сгенерировал НЕВАЛИДНОЕ задание для ежедневного испытания.
Нужно СГЕНЕРИРОВАТЬ ЗАМЕНУ ровно ОДНОГО задания через `add_challenge_item`.

Курс: "{course.title}"
Профиль знаний: {profile_json}

Требуемый тип задания: {desired_type}

Ошибки валидации (их нужно исправить):
{errors_text}

Предыдущее невалидное задание (НЕ повторяй его 1:1):
{prev_json}

КРИТИЧЕСКИЕ ПРАВИЛА:
- Верни результат ТОЛЬКО через tool call `add_challenge_item` ОДИН раз.
- Поля должны соответствовать контракту (item_type, title, question, explanation и т.д.).
"""
        model = self._get_model(tools=self._tools_add_challenge_item())
        response = model.generate_content(prompt, stream=False)
        items = self._extract_items_from_response(response, limit=1)
        return items[0] if items else None

    def generate_full_challenge_validated(self, course, knowledge_profile, count=15):
        """
        Генерирует ежедневное испытание из count заданий.
        Если модель генерирует невалидный item — мы отправляем ей ошибки и просим перегенерировать.
        """
        items = self._generate_items_once(course, knowledge_profile, count=count)
        if len(items) != count:
            raise ValueError(f"Нейросеть вернула {len(items)}/{count} заданий")

        fixed_items = []
        for idx, item in enumerate(items):
            desired_type = item.get("item_type") or "mcq-single"
            errors = self._validate_item(item)
            if not errors:
                fixed_items.append(item)
                continue

            attempts = 0
            regenerated = None
            last_item = item
            last_errors = errors
            while attempts < 3:
                attempts += 1
                regenerated = self._regenerate_single_item(
                    course,
                    knowledge_profile,
                    desired_type=desired_type,
                    validation_errors=last_errors,
                    previous_item=last_item,
                )
                if not regenerated:
                    last_errors = ["модель не вернула tool call add_challenge_item"]
                    continue
                reg_errors = self._validate_item(regenerated)
                if not reg_errors:
                    break
                last_item = regenerated
                last_errors = reg_errors

            if not regenerated or self._validate_item(regenerated):
                raise ValueError(
                    f"Не удалось получить валидное задание #{idx+1} (type={desired_type}). Ошибки: {last_errors}"
                )

            fixed_items.append(regenerated)

        return fixed_items

    def _build_profile_prompt(self, course_title, progress_data, existing_summary):
        progress_json = json.dumps(progress_data, ensure_ascii=False, indent=2)

        existing_part = ''
        if existing_summary:
            existing_part = f"""
ПРЕДЫДУЩИЙ ПРОФИЛЬ ЗНАНИЙ:
{existing_summary}

Обнови профиль с учётом новых данных. Сохрани актуальные сильные/слабые стороны из предыдущего профиля.
"""

        return f"""
Ты — AI-ассистент образовательной платформы по изучению японского языка.
Проанализируй прогресс ученика на курсе "{course_title}" и составь профиль его знаний.

ДАННЫЕ О ПРОГРЕССЕ (последние тесты):
{progress_json}
{existing_part}
Составь профиль знаний, учитывая:
- Какие темы ученик освоил хорошо (strengths)
- В каких темах есть пробелы (weaknesses)  
- Какие темы рекомендуется повторить (recommended_topics)
- Общий уровень ученика (difficulty_level: beginner/intermediate/advanced)
- Краткое резюме (summary) на русском языке

Будь конкретным и опирайся на данные тестов.
"""

    def _build_challenge_prompt(self, course_title, knowledge_profile):
        profile_json = json.dumps(knowledge_profile, ensure_ascii=False, indent=2)

        return f"""
Ты — AI-ассистент образовательной платформы по изучению японского языка.
Сгенерируй ежедневное испытание для ученика курса "{course_title}".

ПРОФИЛЬ ЗНАНИЙ УЧЕНИКА:
{profile_json}

ПРАВИЛА ГЕНЕРАЦИИ:
1. Сгенерируй 15-20 тестовых заданий разных типов
2. Типы заданий:
   - "mcq-single" — выбор одного ответа (question + options + correct_answer)
   - "mcq-multi" — выбор нескольких ответов (question + options + correct_answers)
   - "word-order" — составить предложение из слов (question + correct_order, options = слова вразброс)
   - "drag-and-drop" — сопоставить пары (question + pairs + options = все варианты ответов)
   - "free-text" — написать ответ текстом (question + correct_answer)
3. Распределение: ~40% mcq-single, ~15% mcq-multi, ~15% word-order, ~15% drag-and-drop, ~15% free-text
4. Сложность: 30% easy, 50% medium, 20% hard
5. Фокус на слабых сторонах ученика, но с вкраплениями сильных тем для уверенности
6. Все вопросы ДОЛЖНЫ быть связаны с японским языком
7. Инструкции (title) — на русском, вопросы могут включать японский текст
8. Для каждого задания обязательно explanation — пояснение ответа на русском

Если считаешь, что к какому-то заданию подошла бы картинка или аудио, укажи media_prompt
с описанием того, что нужно сгенерировать. Это будет использовано позже.

ВАЖНО: 
- Каждое задание должно иметь чёткий правильный ответ
- options для MCQ — 3-5 вариантов
- correct_order для word-order — список слов в правильном порядке
- pairs для drag-and-drop — список пар {{prompt, answer}}
"""

    def _build_blitz_prompt(self, course_title):
        return f"""
Ты — AI-ассистент образовательной платформы по изучению японского языка.
Сгенерируй 10 простых и быстрых MCQ-тестов по курсу "{course_title}".

Это блиц-тесты для развлечения. Они должны быть:
- Простыми (уровень easy-medium)
- Быстрыми (одно-два слова в вопросе и ответах)
- Интересными (факты о Японии, перевод слов, грамматика)
- С 4 вариантами ответов каждый
- correct_index — индекс правильного ответа (0-3)
- explanation — краткое пояснение

Примеры тем: перевод слова, чтение кандзи, выбор частицы, факт о культуре.
"""
