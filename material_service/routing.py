from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^api/v1/ws/conversation/(?P<test_id>\d+)/$', consumers.AiConversationConsumer.as_asgi()),
    re_path(r'^api/v1/ws/submission/(?P<submission_id>\d+)/$', consumers.TestSubmissionConsumer.as_asgi()),
]
