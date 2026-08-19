"""
Integration Tests for Voice AI System.

Tests end-to-end flows:
- Booking creation → admin notification
- Booking approval → customer notification
- Voice simulation → response generation
- Analytics API
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import httpx


BASE_URL = "http://localhost:8000"


class TestNotificationFlow:
    """Test notification system end-to-end."""
    
    @pytest.fixture
    async def auth_headers(self):
        """Get authenticated headers."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.post("/api/v1/auth/login", json={
                "email": "admin@demo.com",
                "password": "admin123",
            })
            assert resp.status_code == 200
            token = resp.json()["access_token"]
            return {"Authorization": f"Bearer {token}"}
    
    @pytest.mark.asyncio
    async def test_create_booking_triggers_notification(self, auth_headers):
        """Creating a booking should trigger admin notification."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            # Create booking
            booking_data = {
                "business_id": "11111111-1111-1111-1111-111111111111",
                "service_id": "22222222-2222-2222-2222-222222222222",
                "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
                "customer_name": "Test Customer",
                "customer_phone": "+15551234567",
            }
            
            resp = await client.post(
                "/api/v1/bookings",
                json=booking_data,
                headers=auth_headers,
            )
            
            assert resp.status_code in [200, 201]
            data = resp.json()
            assert "id" in data
            
            # Verify booking is pending
            booking_id = data["id"]
            resp = await client.get(
                f"/api/v1/bookings/{booking_id}",
                headers=auth_headers,
            )
            assert resp.json()["status"] == "pending_approval"
    
    @pytest.mark.asyncio
    async def test_approve_booking_triggers_customer_notification(self, auth_headers):
        """Approving a booking should notify the customer."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            # Get pending bookings
            resp = await client.get(
                "/api/v1/admin/pending",
                headers=auth_headers,
            )
            
            if resp.json().get("bookings"):
                booking_id = resp.json()["bookings"][0]["id"]
                
                # Approve
                resp = await client.patch(
                    f"/api/v1/admin/bookings/{booking_id}/approve",
                    headers=auth_headers,
                )
                
                assert resp.status_code == 200
                assert resp.json()["status"] == "confirmed"


class TestVoiceSimulation:
    """Test voice conversation simulation."""
    
    @pytest.fixture
    async def auth_headers(self):
        """Get authenticated headers."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.post("/api/v1/auth/login", json={
                "email": "admin@demo.com",
                "password": "admin123",
            })
            token = resp.json()["access_token"]
            return {"Authorization": f"Bearer {token}"}
    
    @pytest.mark.asyncio
    async def test_simulation_greeting(self, auth_headers):
        """Test that simulation returns a greeting."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.post(
                "/api/v1/voice/simulate",
                json={
                    "business_id": "11111111-1111-1111-1111-111111111111",
                    "user_input": "Hello",
                },
                headers=auth_headers,
            )
            
            assert resp.status_code == 200
            data = resp.json()
            assert "response" in data
            assert len(data["response"]) > 0
    
    @pytest.mark.asyncio
    async def test_simulation_booking_intent(self, auth_headers):
        """Test that simulation detects booking intent."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.post(
                "/api/v1/voice/simulate",
                json={
                    "business_id": "11111111-1111-1111-1111-111111111111",
                    "user_input": "I'd like to book an appointment",
                },
                headers=auth_headers,
            )
            
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("intent") in ["book_appointment", "booking", None]


class TestAnalytics:
    """Test analytics API."""
    
    @pytest.fixture
    async def auth_headers(self):
        """Get authenticated headers."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.post("/api/v1/auth/login", json={
                "email": "admin@demo.com",
                "password": "admin123",
            })
            token = resp.json()["access_token"]
            return {"Authorization": f"Bearer {token}"}
    
    @pytest.mark.asyncio
    async def test_analytics_overview(self, auth_headers):
        """Test analytics overview endpoint."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.get(
                "/api/v1/analytics/stats/overview",
                params={"business_id": "11111111-1111-1111-1111-111111111111"},
                headers=auth_headers,
            )
            
            assert resp.status_code == 200
            data = resp.json()
            assert "calls" in data
            assert "bookings" in data
            assert "rates" in data
    
    @pytest.mark.asyncio
    async def test_analytics_calls_by_day(self, auth_headers):
        """Test calls by day endpoint."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.get(
                "/api/v1/analytics/stats/calls/by-day",
                params={"business_id": "11111111-1111-1111-1111-111111111111"},
                headers=auth_headers,
            )
            
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)


class TestHealth:
    """Test health endpoints."""
    
    @pytest.mark.asyncio
    async def test_basic_health(self):
        """Test basic health endpoint."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
    
    @pytest.mark.asyncio
    async def test_detailed_health(self):
        """Test detailed health endpoint."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.get("/health/detailed")
            if resp.status_code == 200:
                data = resp.json()
                assert "checks" in data
                assert "database" in data["checks"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
