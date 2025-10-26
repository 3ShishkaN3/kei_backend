from rest_framework import permissions
from course_service.models import CourseTeacher, CourseAssistant


class CanViewOwnProgress(permissions.BasePermission):
    """Разрешает пользователю просматривать только свой прогресс"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Пользователь может просматривать только свой прогресс
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'student'):
            return obj.student == request.user
        return False


class CanViewStudentProgress(permissions.BasePermission):
    """Разрешает преподавателям и администраторам просматривать прогресс студентов"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['admin', 'teacher', 'assistant']
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # Администраторы могут просматривать любой прогресс
        if user.role == 'admin':
            return True
        
        # Преподаватели и помощники могут просматривать прогресс только своих студентов
        if hasattr(obj, 'user'):
            student = obj.user
        elif hasattr(obj, 'student'):
            student = obj.student
        else:
            return False
        
        # Проверяем, является ли пользователь преподавателем или помощником курса студента
        if user.role == 'teacher':
            return CourseTeacher.objects.filter(
                teacher=user,
                course__enrollments__student=student
            ).exists()
        elif user.role == 'assistant':
            return CourseAssistant.objects.filter(
                assistant=user,
                course__enrollments__student=student
            ).exists()
        
        return False


class CanViewCourseProgress(permissions.BasePermission):
    """Разрешает просматривать прогресс по курсу"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # Администраторы могут просматривать любой прогресс
        if user.role == 'admin':
            return True
        
        # Пользователь может просматривать свой прогресс
        if hasattr(obj, 'user') and obj.user == user:
            return True
        
        # Преподаватели и помощники могут просматривать прогресс по своим курсам
        if user.role in ['teacher', 'assistant']:
            if hasattr(obj, 'course'):
                course = obj.course
            elif hasattr(obj, 'lesson') and hasattr(obj.lesson, 'course'):
                course = obj.lesson.course
            else:
                return False
            
            if user.role == 'teacher':
                return CourseTeacher.objects.filter(teacher=user, course=course).exists()
            elif user.role == 'assistant':
                return CourseAssistant.objects.filter(assistant=user, course=course).exists()
        
        return False


class CanViewLeaderboard(permissions.BasePermission):
    """Разрешает просматривать рейтинги"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated
