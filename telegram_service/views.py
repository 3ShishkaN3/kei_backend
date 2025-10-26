from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from .serializers import ConsultationRequestSerializer
from .utils import send_telegram_message

class ConsultationRequestView(GenericAPIView):
    serializer_class = ConsultationRequestSerializer
    permission_classes = [] 

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            message = (
                f"Новый запрос на консультацию!\n"
                f"Пользователь: {data['username']}\n"
                f"Тема: {data['subject']}\n"
                f"Электронная почта: {data['email']}"
            )
            try:
                send_telegram_message(message)
            except Exception:
                return Response(
                    {"error": "Не удалось отправить запрос, попробуйте позже."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            return Response({"message": "Запрос успешно отправлен."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
