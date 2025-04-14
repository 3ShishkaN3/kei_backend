from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .permissions import IsAdminTeacherAssistantOrReadOnly, IsAdminTeacherOrReadOnly
from .models import Course, CourseTeacher, CourseAssistant, CourseEnrollment
from .utils import send_to_kafka
from .serializers import (
    CourseListSerializer,
    CourseDetailSerializer,
    CourseTeacherSerializer,
    CourseAssistantSerializer,
    CourseEnrollmentSerializer
)

class CourseViewSet(viewsets.ModelViewSet):
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'title']
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = Course.objects.all()
        
        if self.request.user.is_authenticated and self.request.user.role in ['admin', 'teacher', 'assistant']:
            status_filter = self.request.query_params.get('status')
            if status_filter:
                queryset = queryset.filter(status=status_filter)
        else:
            queryset = queryset.filter(status='published')
        
        created_by = self.request.query_params.get('created_by')
        if created_by:
            queryset = queryset.filter(created_by_id=created_by)
            
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'list':
            return CourseListSerializer
        return CourseDetailSerializer
    
    def get_permissions(self):
        if self.action in ['destroy']:
            permission_classes = [IsAuthenticated, IsAdminTeacherOrReadOnly]
        else:
            permission_classes = [IsAuthenticated, IsAdminTeacherAssistantOrReadOnly]
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
        
    @action(detail=True, methods=['post'])
    def enroll(self, request, pk=None):
        course = self.get_object()
        user = request.user
        
        if CourseTeacher.objects.filter(course=course, teacher=user).exists() or \
            CourseAssistant.objects.filter(course=course, assistant=user).exists():
                return Response(
                    {"error": "Вы не можете записаться на курс, так как являетесь преподавателем или помощником"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        enrollment, created = CourseEnrollment.objects.get_or_create(
            course=course,
            student=user,
            defaults={'status': 'active'}
        )
        
        if not created:
            if enrollment.status == 'active':
                return Response(
                    {"error": "Вы уже записаны на этот курс"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                enrollment.status = 'active'
                enrollment.save()
        
        send_to_kafka('course_events', {
            'type': 'enrollment',
            'user_id': user.id,
            'course_id': course.id,
            'timestamp': timezone.now().isoformat()
        })
        
        return Response({
            "success": "Вы успешно записались на курс",
            "enrollment": CourseEnrollmentSerializer(enrollment).data
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        course = self.get_object()
        user = request.user
        
        try:
            enrollment = CourseEnrollment.objects.get(course=course, student=user, status='active')
            enrollment.status = 'dropped'
            enrollment.save()
            
            send_to_kafka('course_events', {
                'type': 'leave_course',
                'user_id': user.id,
                'course_id': course.id,
                'timestamp': timezone.now().isoformat()
            })
            
            return Response({"success": "Вы отчислены из курса"})
        except CourseEnrollment.DoesNotExist:
            return Response(
                {"error": "Вы не записаны на этот курс"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        course = self.get_object()
        user = request.user
        
        try:
            enrollment = CourseEnrollment.objects.get(course=course, student=user, status='active')
            enrollment.status = 'completed'
            enrollment.completed_at = timezone.now()
            enrollment.save()
            
            send_to_kafka('course_events', {
                'type': 'course_completed',
                'user_id': user.id,
                'course_id': course.id,
                'timestamp': timezone.now().isoformat()
            })
            
            return Response({"success": "Поздравляем с завершением курса!"})
        except CourseEnrollment.DoesNotExist:
            return Response(
                {"error": "Вы не записаны на этот курс"},
                status=status.HTTP_400_BAD_REQUEST
            )


class CourseTeacherViewSet(viewsets.ModelViewSet):
    serializer_class = CourseTeacherSerializer
    permission_classes = [IsAuthenticated, IsAdminTeacherOrReadOnly]
    
    def get_queryset(self):
        course_id = self.kwargs.get('course_pk')
        return CourseTeacher.objects.filter(course_id=course_id)
    
    def perform_create(self, serializer):
        course = get_object_or_404(Course, pk=self.kwargs.get('course_pk'))
        serializer.save(course=course)
        
        send_to_kafka('course_events', {
            'type': 'teacher_assigned',
            'user_id': serializer.validated_data['teacher'].id,
            'course_id': course.id,
            'timestamp': timezone.now().isoformat()
        })


class CourseAssistantViewSet(viewsets.ModelViewSet):
    serializer_class = CourseAssistantSerializer
    permission_classes = [IsAuthenticated, IsAdminTeacherOrReadOnly]
    
    def get_queryset(self):
        course_id = self.kwargs.get('course_pk')
        return CourseAssistant.objects.filter(course_id=course_id)
    
    def perform_create(self, serializer):
        course = get_object_or_404(Course, pk=self.kwargs.get('course_pk'))
        serializer.save(course=course)
        
        send_to_kafka('course_events', {
            'type': 'assistant_assigned',
            'user_id': serializer.validated_data['assistant'].id,
            'course_id': course.id,
            'timestamp': timezone.now().isoformat()
        })


class CourseEnrollmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseEnrollmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['student__username', 'student__email']
    ordering_fields = ['enrolled_at', 'status']
    ordering = ['-enrolled_at']
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            queryset = CourseEnrollment.objects.all()
        elif user.role == 'teacher':
            teacher_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            queryset = CourseEnrollment.objects.filter(course_id__in=teacher_courses)
        elif user.role == 'assistant':
            assistant_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            queryset = CourseEnrollment.objects.filter(course_id__in=assistant_courses)
        else:
            queryset = CourseEnrollment.objects.filter(student=user)
            
        course_id = self.request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(course_id=course_id)
            
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
            
        return queryset