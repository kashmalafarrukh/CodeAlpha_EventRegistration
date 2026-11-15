from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Event, Registration
from .serializers import (AttendeeSerializer, EventSerializer,
                          RegistrationSerializer, SignupSerializer)


class IsOrganizerOrReadOnly(permissions.BasePermission):
    """Anyone can read. Only staff can create. Only the organizer can edit/delete."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.is_staff

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.organizer == request.user


class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer
    permission_classes = [permissions.AllowAny]


class EventListCreateView(generics.ListCreateAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsOrganizerOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(organizer=self.request.user)


class EventDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsOrganizerOrReadOnly]


class RegisterForEventView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        with transaction.atomic():
            event = get_object_or_404(Event.objects.select_for_update(), pk=pk)

            if event.date <= timezone.now():
                return Response({"error": "This event has already happened."},
                                status=status.HTTP_400_BAD_REQUEST)

            registration = Registration.objects.filter(
                user=request.user, event=event).first()

            if registration and registration.status == Registration.CONFIRMED:
                return Response({"error": "You are already registered for this event."},
                                status=status.HTTP_409_CONFLICT)

            if event.seats_left == 0:
                return Response({"error": "This event is full."},
                                status=status.HTTP_400_BAD_REQUEST)

            if registration:  # re-registering after a cancellation
                registration.status = Registration.CONFIRMED
                registration.save()
            else:
                registration = Registration.objects.create(
                    user=request.user, event=event)

        return Response(RegistrationSerializer(registration).data,
                        status=status.HTTP_201_CREATED)


class MyRegistrationsView(generics.ListAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Registration.objects.filter(
            user=self.request.user).select_related("event")


class RegistrationDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        registration = get_object_or_404(Registration, pk=pk, user=request.user)
        return Response(RegistrationSerializer(registration).data)

    def delete(self, request, pk):
        """Cancel a registration. Users can only cancel their own."""
        registration = get_object_or_404(Registration, pk=pk, user=request.user)
        if registration.status == Registration.CANCELLED:
            return Response({"error": "Registration is already cancelled."},
                            status=status.HTTP_400_BAD_REQUEST)
        registration.status = Registration.CANCELLED
        registration.save()
        return Response({"detail": "Registration cancelled."})


class EventAttendeesView(generics.ListAPIView):
    """Organizers can see who registered for their own events."""
    serializer_class = AttendeeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        event = get_object_or_404(Event, pk=self.kwargs["pk"],
                                  organizer=self.request.user)
        return event.registrations.select_related("user")
