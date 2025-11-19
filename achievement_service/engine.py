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
            # If no rules, maybe it's manual or always true? 
            # For now assume empty rules = False to be safe
            return False

        try:
            return json_logic.jsonLogic(achievement.compiled_rules, context)
        except Exception as e:
            print(f"Error evaluating achievement {achievement.id}: {e}")
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
        # 1. Filter achievements that *might* be triggered.
        # Optimization: We could store "trigger_event" in Achievement model to filter faster.
        # For now, we'll fetch all active achievements and let json-logic decide,
        # OR we can assume the rule structure has a "trigger" field at the top level.
        
        # Let's assume the compiled_rules has a structure like:
        # { "and": [ { "==": [ {"var": "trigger"}, "ON_LESSON_COMPLETE" ] }, ... ] }
        # So we add "trigger": event_type to the context.
        
        context['trigger'] = event_type
        
        # Get all active achievements not yet awarded to this user
        existing_ids = UserAchievement.objects.filter(user=user).values_list('achievement_id', flat=True)
        candidates = Achievement.objects.filter(is_active=True).exclude(id__in=existing_ids)
        
        newly_awarded = []
        
        for achievement in candidates:
            if RuleEngine.evaluate(achievement, context):
                ua = UserAchievement.objects.create(user=user, achievement=achievement)
                newly_awarded.append(ua)
                
        return newly_awarded
