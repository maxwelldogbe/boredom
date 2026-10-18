"""WebSocket URL routes: the single /ws/ endpoint."""

from django.urls import URLPattern, path

from rooms.consumers import RoomConsumer

websocket_urlpatterns: list[URLPattern] = [path("ws/", RoomConsumer.as_asgi())]
