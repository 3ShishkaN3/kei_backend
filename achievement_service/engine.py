import json_logic
from .models import Achievement, UserAchievement

class RuleEngine:
    @staticmethod
    def evaluate(achievement, context):
        """
        Evaluates the achievement rules against the given context.
        :param achievement: Achievement instance
        :param context: Dictionary containing facts (event data + user state)
        :return: Boolean
        """
        if not achievement.is_active:
            return False
            
        if not achievement.compiled_rules:
            return True

        try:
            print(f"[DEBUG] Evaluating achievement {achievement.id}: {achievement.title}")
            print(f"[DEBUG] Context: {context}")
            
            result = json_logic.jsonLogic(achievement.compiled_rules, context)
            print(f"[DEBUG] Result: {result}")
            return result
        except Exception as e:
            print(f"[ERROR] Error evaluating achievement {achievement.id}: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def check_achievements(user, event_type, context):
        """
        Checks all relevant achievements for a user based on an event.
        :param user: User instance
        :param event_type: String (e.g., 'ON_LESSON_COMPLETE')
        :param context: Dictionary of facts
        :return: List of newly awarded UserAchievement instances
        """
    
        print(f"[DEBUG] check_achievements for user {user.id}, event {event_type}")
        
        all_active = Achievement.objects.filter(is_active=True)
        candidates = []
        for a in all_active:
            for t in a.triggers:
                if t.get('type') == event_type:
                    candidates.append(a)
                    break
        
        print(f"[DEBUG] Found {len(candidates)} candidates with trigger {event_type}")
        
        existing_uas = UserAchievement.objects.filter(user=user).select_related('achievement')
        existing_ids = [ua.achievement_id for ua in existing_uas]
        existing_titles = [ua.achievement.title for ua in existing_uas]
        
        print(f"[DEBUG] User {user.username} (ID: {user.id}) already has: {existing_titles}")
        
        candidates = [c for c in candidates if c.id not in existing_ids]
        print(f"[DEBUG] New candidates to evaluate: {[c.title for c in candidates]}")
        
        newly_awarded = []
        
        for achievement in candidates:
            is_trigger_match = False
            for trigger in achievement.triggers:
                if trigger['type'] != event_type:
                    continue
                
                params = trigger.get('params', {})
                if not params:
                    is_trigger_match = True
                    break
                
                match = True
                for key, value in params.items():
                    if value in [None, ""]: # "Any"
                        continue
                    ctx_val = context.get(key)
                    if ctx_val is None and 'event' in context:
                        ctx_val = context['event'].get(key)
                    if str(ctx_val) != str(value):
                        match = False
                        break
                
                if match:
                    is_trigger_match = True
                    break
            
            if not is_trigger_match:
                continue

            if RuleEngine.evaluate(achievement, context):
                ua = UserAchievement.objects.create(user=user, achievement=achievement)
                newly_awarded.append(ua)
                
        return newly_awarded
