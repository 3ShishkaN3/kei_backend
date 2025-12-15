import json
from channels.generic.websocket import JsonWebsocketConsumer
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model

User = get_user_model()

class NotificationConsumer(JsonWebsocketConsumer):
    def connect(self):
        user = self.scope["user"]
        
        if user.is_authenticated:
            self.user_id = user.id
            self.user_group_name = f'notifications_for_user_{self.user_id}'

            # Присоединяем пользователя к группе
            async_to_sync(self.channel_layer.group_add)(
                self.user_group_name,
                self.channel_name
            )
            self.accept()
            print(f"Пользователь {user.username} подключился к WebSocket и добавлен в группу {self.user_group_name}.")
            self.send_json({"type": "websocket.connected", "message": "Успешно подключены к каналу уведомлений."})
        else:
            self.close() # Закрываем соединение, если пользователь не аутентифицирован
            print("Анонимное WebSocket соединение отклонено.")

    def disconnect(self, close_code):
        user = self.scope.get("user")
        if user and user.is_authenticated:
            # Отключаем пользователя от группы
            async_to_sync(self.channel_layer.group_discard)(
                self.user_group_name,
                self.channel_name
            )
            print(f"Пользователь {user.username} отключился от WebSocket.")

    def receive_json(self, content, **kwargs):
        # Эта логика нам пока не нужна, так как сервер только отправляет, но не принимает команды
        print(f"Получено сообщение от клиента (игнорируется): {content}")
        pass

    def send_notification(self, event):
        # Отправляем уведомление через WebSocket
        print(f"Отправка уведомления в группу: {event}")
        self.send_json({
            "type": "notification",
            "message": event["message"]
        })
