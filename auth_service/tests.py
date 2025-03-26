from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.test import TestCase
from .models import User, ConfirmationCode
from django.contrib.auth import get_user_model

User = get_user_model()

from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from rest_framework import status
from django.test import TestCase


User = get_user_model()

class AuthServiceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse("register")
        self.login_url = reverse("login")
        self.logout_url = reverse("logout")

    def test_registration(self):
        """
        Тестирование сценария регистрации.
        При успешной регистрации ожидается, что:
        - Пользователь создаётся.
        - Возвращается сообщение о том, что на email отправлен код подтверждения.
        - Создан confirmation-код.
        """
        data = {
            "username": "testuser",
            "email": "shishka-danil@mail.ru",
            "password": "Passw0rd123",
            "password2": "Passw0rd123",
            "role": "student"
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("message", response.data)
        self.assertIn("user", response.data)

        user = User.objects.get(email="shishka-danil@mail.ru")
        confirmation_exists = ConfirmationCode.objects.filter(user=user, code_type=ConfirmationCode.REGISTRATION).exists()
        self.assertTrue(confirmation_exists)

    def test_login_logout(self):
        user = User.objects.create_user(
            username="testlogin", 
            email="shishka-danil@mail.ru", 
            password="Passw0rd123",
            role="student"
        )
        login_data = {
            "username": "testlogin",
            "password": "Passw0rd123"
        }
        login_response = self.client.post(self.login_url, login_data, format="json")
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn("message", login_response.data)
        self.assertEqual(login_response.data["message"], "Вы успешно вошли")

        logout_response = self.client.post(self.logout_url, format="json")
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)
        self.assertIn("message", logout_response.data)
        self.assertEqual(logout_response.data["message"], "Вы успешно вышли")

