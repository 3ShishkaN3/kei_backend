from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db.models import Q, Case, When, IntegerField
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from auth_service.models import User
from auth_service.serializers import UserSerializer
from .permissions import IsAdminTeacherAssistantOrReadOnly, IsAdminTeacherOrReadOnly
from .models import Course, CourseTeacher, CourseAssistant, CourseEnrollment
from kei_backend.utils import send_to_kafka
from .serializers import (
    CourseListSerializer,
    CourseDetailSerializer,
    CourseTeacherSerializer,
    CourseAssistantSerializer,
    CourseEnrollmentSerializer,
    BulkEnrollmentSerializer,
    BulkLeaveSerializer
)

class CourseViewSet(viewsets.ModelViewSet):
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'title']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user
        queryset = Course.objects.all()
        
        if user.is_authenticated and user.role in ['admin', 'teacher']:
            status_filter = self.request.query_params.get('status')
            if status_filter:
                queryset = queryset.filter(status=status_filter)
        elif user.is_authenticated and user.role == 'assistant':
            has_enrollments = CourseEnrollment.objects.filter(
                student=user, 
                status='active'
            ).exists()
            
            if has_enrollments:
                enrolled_course_ids = Course.objects.filter(
                    enrollments__student=user, 
                    enrollments__status='active'
                ).values_list('id', flat=True)
                
                queryset = Course.objects.filter(
                    Q(id__in=enrolled_course_ids) |
                    Q(status='free') |
                    Q(status='published')
                ).distinct()
                
                queryset = queryset.annotate(
                    is_enrolled=Case(
                        When(id__in=enrolled_course_ids, then=1),
                        default=0,
                        output_field=IntegerField(),
                    ),
                    course_priority=Case(
                        When(status='published', then=1),
                        When(status='free', then=2),
                        default=3,
                        output_field=IntegerField(),
                    )
                )
                
                queryset = queryset.order_by('is_enrolled', 'course_priority', '-created_at')
            else:
                status_filter = self.request.query_params.get('status')
                if status_filter:
                    queryset = queryset.filter(status=status_filter)
        elif user.is_authenticated and user.role == 'student':
            enrolled_course_ids = Course.objects.filter(
                enrollments__student=user, 
                enrollments__status='active'
            ).values_list('id', flat=True)

            queryset = Course.objects.filter(
                Q(id__in=enrolled_course_ids) |
                Q(status='free') |
                Q(status='published')
            ).distinct()
            
            queryset = queryset.annotate(
                is_enrolled=Case(
                    When(id__in=enrolled_course_ids, then=1),
                    default=0,
                    output_field=IntegerField(),
                ),
                course_priority=Case(
                    When(status='published', then=1),
                    When(status='free', then=2),
                    default=3,
                    output_field=IntegerField(),
                )
            )
            
            queryset = queryset.order_by('is_enrolled', 'course_priority', '-created_at')
        else:
            queryset = queryset.filter(status='published')
        
        created_by = self.request.query_params.get('created_by')
        if created_by:
            queryset = queryset.filter(created_by_id=created_by)
            
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'list':
            return CourseListSerializer
        if self.action == 'bulk_enroll':
            return BulkEnrollmentSerializer
        if self.action == 'bulk_leave':
            return BulkLeaveSerializer
        return CourseDetailSerializer
    
    def get_permissions(self):
        if self.action == 'enroll':
            permission_classes = [IsAuthenticated]
        elif self.action in ['destroy']:
            permission_classes = [IsAuthenticated, IsAdminTeacherOrReadOnly]
        else:
            permission_classes = [IsAuthenticated, IsAdminTeacherAssistantOrReadOnly]
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def enrollment_status(self, request, pk=None):
        course = self.get_object()
        user = request.user

        try:
            enrollment = CourseEnrollment.objects.get(course=course, student=user)
            return Response({
                "enrolled": True,
                "status": enrollment.status,
                "enrollment_id": enrollment.id,
                "enrolled_at": enrollment.enrolled_at,
                "completed_at": enrollment.completed_at
            }, status=status.HTTP_200_OK)
        except CourseEnrollment.DoesNotExist:
            return Response({"enrolled": False}, status=status.HTTP_200_OK)
        
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def enroll(self, request, pk=None):
        course = self.get_object()
        
        student_id = request.data.get('student_id')
        if student_id:
            if request.user.role not in ['admin', 'teacher']:
                return Response(
                    {"error": "Нет прав для записи ученика на курс"},
                    status=status.HTTP_403_FORBIDDEN
                )
            student = get_object_or_404(User, pk=student_id)
        else:
            if course.status != 'free':
                return Response(
                    {"error": "Самостоятельная запись доступна только для бесплатных курсов"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            student = request.user
        
        if CourseTeacher.objects.filter(course=course, teacher=student).exists() or \
           CourseAssistant.objects.filter(course=course, assistant=student).exists():
            return Response(
                {"error": "Невозможно записать на курс, так как пользователь является преподавателем или помощником"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        enrollment, created = CourseEnrollment.objects.get_or_create(
            course=course,
            student=student,
            defaults={'status': 'active'}
        )
        if not created:
            if enrollment.status == 'active':
                return Response(
                    {"error": "Пользователь уже записан на этот курс"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                enrollment.status = 'active'
                enrollment.save()
        
        send_to_kafka('course_events', {
            'type': 'enrollment',
            'user_id': student.id,
            'course_id': course.id,
            'timestamp': timezone.now().isoformat()
        })
        
        return Response({
            "success": "Пользователь успешно записан на курс",
            "enrollment": CourseEnrollmentSerializer(enrollment).data
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        if 'student_id' not in request.data:
            return Response(
                {"error": "Отчисление может быть выполнено только преподавателем или администратором для указанного ученика"},
                status=status.HTTP_403_FORBIDDEN
            )
        student = get_object_or_404(User, pk=request.data['student_id'])
        course = self.get_object()
        
        try:
            enrollment = CourseEnrollment.objects.get(course=course, student=student, status='active')
            enrollment.status = 'dropped'
            enrollment.save()
            
            send_to_kafka('course_events', {
                'type': 'leave_course',
                'user_id': student.id,
                'course_id': course.id,
                'timestamp': timezone.now().isoformat()
            })
            
            return Response({"success": "Пользователь отчислен из курса"})
        except CourseEnrollment.DoesNotExist:
            return Response(
                {"error": "Пользователь не записан на курс или уже отчислен"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        if 'student_id' not in request.data:
            return Response(
                {"error": "Завершение курса может быть выполнено только преподавателем или администратором для указанного ученика"},
                status=status.HTTP_403_FORBIDDEN
            )
        student = get_object_or_404(User, pk=request.data['student_id'])
        course = self.get_object()
        
        try:
            enrollment = CourseEnrollment.objects.get(course=course, student=student, status='active')
            enrollment.status = 'completed'
            enrollment.completed_at = timezone.now()
            enrollment.save()
            
            success = send_to_kafka('course_events', {
                'type': 'course_completed',
                'user_id': student.id,
                'course_id': course.id,
                'timestamp': timezone.now().isoformat()
            })
            if not success:
                print(f"Не удалось отправить событие course_completed для курса {course.id}")
            
            return Response({"success": "Курс успешно завершён для ученика"})
        except CourseEnrollment.DoesNotExist:
            return Response(
                {"error": "Пользователь не записан на курс или курс уже завершён/отчислен"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], serializer_class=BulkEnrollmentSerializer)
    def bulk_enroll(self, request, pk=None):
        """
        Массовая запись учеников на курс.
        
        Принимает список student_ids и записывает всех учеников на курс.
        """
        if request.user.role not in ['admin', 'teacher']:
            return Response(
                {"error": "Нет прав для записи учеников на курс"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        course = self.get_object()
        student_ids = serializer.validated_data['student_ids']
        students = User.objects.filter(id__in=student_ids, role=User.Role.STUDENT)
        
        if students.count() != len(student_ids):
            return Response(
                {"error": "Некоторые ID не принадлежат ученикам или не найдены"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created_count = 0
        updated_count = 0
        errors = []
        
        for student in students:
            if CourseTeacher.objects.filter(course=course, teacher=student).exists() or \
               CourseAssistant.objects.filter(course=course, assistant=student).exists():
                errors.append(f"{student.username} является преподавателем или помощником курса")
                continue
            
            enrollment, created = CourseEnrollment.objects.get_or_create(
                course=course,
                student=student,
                defaults={'status': 'active'}
            )
            
            if created:
                created_count += 1
                send_to_kafka('course_events', {
                    'type': 'enrollment',
                    'user_id': student.id,
                    'course_id': course.id,
                    'timestamp': timezone.now().isoformat()
                })
            elif enrollment.status != 'active':
                enrollment.status = 'active'
                enrollment.save()
                updated_count += 1
                send_to_kafka('course_events', {
                    'type': 'enrollment',
                    'user_id': student.id,
                    'course_id': course.id,
                    'timestamp': timezone.now().isoformat()
                })
        
        response_data = {
            "message": f"Записано новых: {created_count}, обновлено: {updated_count}",
            "created_count": created_count,
            "updated_count": updated_count
        }
        
        if errors:
            response_data["errors"] = errors
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], serializer_class=BulkLeaveSerializer)
    def bulk_leave(self, request, pk=None):
        """
        Массовое отчисление учеников с курса.
        
        Принимает список student_ids и отчисляет всех учеников с курса.
        """
        if request.user.role not in ['admin', 'teacher']:
            return Response(
                {"error": "Нет прав для отчисления учеников с курса"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        course = self.get_object()
        student_ids = serializer.validated_data['student_ids']
        
        enrollments = CourseEnrollment.objects.filter(
            course=course,
            student_id__in=student_ids,
            status='active'
        )
        
        updated_count = enrollments.count()
        
        for enrollment in enrollments:
            enrollment.status = 'dropped'
            enrollment.save()
            
            send_to_kafka('course_events', {
                'type': 'leave_course',
                'user_id': enrollment.student.id,
                'course_id': course.id,
                'timestamp': timezone.now().isoformat()
            })
        
        return Response({
            "message": f"Отчислено учеников: {updated_count}",
            "updated_count": updated_count
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def student_statistics(self, request):
        """
        Получение статистики по ученику.
        
        Параметры:
        - student_id: ID ученика (обязательно)
        
        Возвращает статистику по записям ученика на курсы.
        """
        if request.user.role not in ['admin', 'teacher']:
            return Response(
                {"error": "Нет прав для просмотра статистики учеников"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response(
                {"error": "student_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            student = User.objects.get(id=student_id, role=User.Role.STUDENT)
        except User.DoesNotExist:
            return Response(
                {"error": "Ученик не найден"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if request.user.role == 'teacher':
            teacher_courses = CourseTeacher.objects.filter(teacher=request.user).values_list('course_id', flat=True)
            enrollments = CourseEnrollment.objects.filter(
                student=student,
                course_id__in=teacher_courses
            )
        else:
            enrollments = CourseEnrollment.objects.filter(student=student)
        
        total_courses = enrollments.count()
        active_courses = enrollments.filter(status='active').count()
        completed_courses = enrollments.filter(status='completed').count()
        dropped_courses = enrollments.filter(status='dropped').count()
        
        enrollment_data = CourseEnrollmentSerializer(enrollments, many=True).data
        
        return Response({
            "student": UserSerializer(student).data,
            "statistics": {
                "total_courses": total_courses,
                "active_courses": active_courses,
                "completed_courses": completed_courses,
                "dropped_courses": dropped_courses
            },
            "enrollments": enrollment_data
        }, status=status.HTTP_200_OK)

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
