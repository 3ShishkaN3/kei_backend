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
            # If no rules, but it has triggers... 
            # If it was triggered, and there are no additional conditions, it should be awarded.
            # (e.g. "On Lesson Complete" -> Award)
            return True

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
        # 1. Filter achievements that are triggered by this event.
        # We look for achievements where 'triggers' list contains an entry with matching 'type'.
        # And if params are specified, they must match.
        
        # This filtering is a bit complex for pure SQL if triggers is a list of dicts.
        # But we can filter by "triggers__contains" if we construct the partial object?
        # No, because params might be partial.
        
        # Better approach: Filter by type first, then refine in Python.
        # We assume 'triggers' is a list of dicts: [{'type': '...', 'params': {...}}]
        
        # Django's JSONField lookups:
        # Achievement.objects.filter(triggers__contains=[{'type': event_type}])
        # This works if the dict matches exactly or is a subset? Postgres JSONB supports containment.
        # SQLite supports it too in recent versions.
        
        candidates = Achievement.objects.filter(
            is_active=True,
            triggers__contains=[{'type': event_type}] 
        )
        
        # Exclude already awarded
        existing_ids = UserAchievement.objects.filter(user=user).values_list('achievement_id', flat=True)
        candidates = candidates.exclude(id__in=existing_ids)
        
        newly_awarded = []
        
        for achievement in candidates:
            # 2. Check specific trigger parameters
            # e.g. if achievement requires lesson_id=5, and context has lesson_id=5 -> Match.
            # if achievement requires lesson_id=5, and context has lesson_id=6 -> No Match.
            # if achievement has NO params (Any lesson), and context has lesson_id=6 -> Match.
            
            is_trigger_match = False
            for trigger in achievement.triggers:
                if trigger['type'] != event_type:
                    continue
                
                params = trigger.get('params', {})
                if not params:
                    is_trigger_match = True
                    break
                
                # Check all params
                match = True
                for key, value in params.items():
                    if value is None: # "Any"
                        continue
                    # Value in context might be int, value in params might be string/int
                    ctx_val = context.get(key)
                    if str(ctx_val) != str(value):
                        match = False
                        break
                
                if match:
                    is_trigger_match = True
                    break
            
            if not is_trigger_match:
                continue

            # 3. Evaluate Conditions
            if RuleEngine.evaluate(achievement, context):
                ua = UserAchievement.objects.create(user=user, achievement=achievement)
                newly_awarded.append(ua)
                
        return newly_awarded
