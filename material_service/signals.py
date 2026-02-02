from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import TestSubmission

@receiver(post_save, sender=TestSubmission)
def notify_submission_update(sender, instance, created, **kwargs):
    """
    Отправляет уведомление в WebSocket группу при обновлении статуса отправки.
    Группа формируется как: submission_{id}
    """
    
    channel_layer = get_channel_layer()
    group_name = f"submission_{instance.id}"
    
    data = {
        "type": "submission_update",
        "submission": {
            "id": instance.id,
            "status": instance.status,
            "score": float(instance.score) if instance.score is not None else None,
            "feedback": instance.feedback,
            "submitted_at": instance.submitted_at.isoformat() if instance.submitted_at else None
        }
    }
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "send_update",
            "content": data
        }
    )
