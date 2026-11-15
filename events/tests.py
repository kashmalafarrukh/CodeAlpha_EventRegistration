from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Event


class EventAPITests(APITestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(
            "organizer", password="Pass12345!", is_staff=True)
        self.ali = User.objects.create_user("ali", password="Pass12345!")
        self.sara = User.objects.create_user("sara", password="Pass12345!")
        self.event = Event.objects.create(
            title="Meetup", venue="Hall",
            date=timezone.now() + timedelta(days=5),
            capacity=1, organizer=self.organizer)

    def login(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

    def register(self, user):
        self.login(user)
        return self.client.post(f"/api/events/{self.event.id}/register/")

    def test_event_list_is_public(self):
        response = self.client.get("/api/events/")
        self.assertEqual(response.status_code, 200)

    def test_anonymous_cannot_register(self):
        response = self.client.post(f"/api/events/{self.event.id}/register/")
        self.assertEqual(response.status_code, 401)

    def test_user_can_register(self):
        response = self.register(self.ali)
        self.assertEqual(response.status_code, 201)

    def test_duplicate_registration_is_rejected(self):
        self.register(self.ali)
        response = self.register(self.ali)
        self.assertEqual(response.status_code, 409)

    def test_full_event_is_rejected(self):
        self.register(self.ali)
        response = self.register(self.sara)
        self.assertEqual(response.status_code, 400)

    def test_cancel_frees_the_seat(self):
        first = self.register(self.ali)
        self.client.delete(f"/api/registrations/{first.data['id']}/")
        response = self.register(self.sara)
        self.assertEqual(response.status_code, 201)

    def test_user_can_register_again_after_cancelling(self):
        first = self.register(self.ali)
        self.client.delete(f"/api/registrations/{first.data['id']}/")
        response = self.register(self.ali)
        self.assertEqual(response.status_code, 201)

    def test_cannot_cancel_someone_elses_registration(self):
        first = self.register(self.ali)
        self.login(self.sara)
        response = self.client.delete(f"/api/registrations/{first.data['id']}/")
        self.assertEqual(response.status_code, 404)

    def test_my_registrations_shows_only_my_own(self):
        self.register(self.ali)
        self.login(self.sara)
        response = self.client.get("/api/registrations/")
        self.assertEqual(len(response.data), 0)

    def test_normal_user_cannot_create_event(self):
        self.login(self.ali)
        response = self.client.post("/api/events/", {
            "title": "X", "venue": "Y", "capacity": 5,
            "date": (timezone.now() + timedelta(days=2)).isoformat(),
        })
        self.assertEqual(response.status_code, 403)

    def test_staff_can_create_event(self):
        self.login(self.organizer)
        response = self.client.post("/api/events/", {
            "title": "New", "venue": "Room", "capacity": 5,
            "date": (timezone.now() + timedelta(days=2)).isoformat(),
        })
        self.assertEqual(response.status_code, 201)

    def test_event_in_the_past_is_rejected(self):
        self.login(self.organizer)
        response = self.client.post("/api/events/", {
            "title": "Old", "venue": "Room", "capacity": 5,
            "date": (timezone.now() - timedelta(days=2)).isoformat(),
        })
        self.assertEqual(response.status_code, 400)

    def test_only_organizer_sees_attendees(self):
        self.register(self.ali)
        self.login(self.ali)
        denied = self.client.get(f"/api/events/{self.event.id}/attendees/")
        self.assertEqual(denied.status_code, 404)
        self.login(self.organizer)
        allowed = self.client.get(f"/api/events/{self.event.id}/attendees/")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(len(allowed.data), 1)