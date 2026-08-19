"""
Pydantic models for data validation and serialization.
These models are used for API requests/responses and business logic.
"""

from datetime import datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ============================================
# ENUMS
# ============================================

class BookingStatus(str, Enum):
    """Booking status options."""
    PENDING_APPROVAL = "pending_approval"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class OrderStatus(str, Enum):
    """Order status options."""
    PENDING_APPROVAL = "pending_approval"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RequestStatus(str, Enum):
    """Service request status options."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RequestPriority(str, Enum):
    """Service request priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ConversationStatus(str, Enum):
    """Conversation session status."""
    ACTIVE = "active"
    COMPLETED = "completed"
    TRANSFERRED = "transferred"
    FAILED = "failed"


class ChannelType(str, Enum):
    """Communication channel types."""
    PHONE = "phone"
    WEB = "web"
    MOBILE = "mobile"


class ResourceType(str, Enum):
    """Resource types."""
    STAFF = "staff"
    ROOM = "room"
    EQUIPMENT = "equipment"


class UserRole(str, Enum):
    """Admin user roles."""
    OWNER = "owner"
    MANAGER = "manager"
    STAFF = "staff"


class BookingSource(str, Enum):
    """Booking source types."""
    VOICE_AI = "voice_ai"
    WEB = "web"
    MOBILE = "mobile"
    MANUAL = "manual"


# ============================================
# BASE MODELS
# ============================================

class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    model_config = ConfigDict(from_attributes=True)


class TimestampMixin(BaseModel):
    """Mixin for created_at and updated_at fields."""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None


# ============================================
# BUSINESS
# ============================================

class BusinessBase(BaseSchema):
    """Base business model."""
    name: str = Field(..., min_length=1, max_length=255)
    timezone: str = Field(default="UTC", max_length=50)
    phone_number: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    settings: Dict[str, Any] = Field(default_factory=dict)


class BusinessCreate(BusinessBase):
    """Create business request."""
    pass


class Business(BusinessBase, TimestampMixin):
    """Business model with ID."""
    id: UUID


# ============================================
# USER (CALLER/CUSTOMER)
# ============================================

class UserBase(BaseSchema):
    """Base user model."""
    phone: str = Field(..., max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)
    preferred_contact: str = Field(default="sms", max_length=20)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UserCreate(UserBase):
    """Create user request."""
    business_id: UUID


class User(UserBase, TimestampMixin):
    """User model with ID."""
    id: UUID
    business_id: UUID


# ============================================
# ADMIN USER
# ============================================

class AdminUserBase(BaseSchema):
    """Base admin user model."""
    email: str = Field(..., max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)
    role: UserRole = Field(default=UserRole.STAFF)
    notification_preferences: Dict[str, bool] = Field(
        default_factory=lambda: {"sms": True, "email": True, "push": True}
    )
    is_active: bool = Field(default=True)


class AdminUserCreate(AdminUserBase):
    """Create admin user request."""
    business_id: UUID
    password: str = Field(..., min_length=8)


class AdminUser(AdminUserBase, TimestampMixin):
    """Admin user model with ID."""
    id: UUID
    business_id: UUID


class AdminUserLogin(BaseSchema):
    """Admin login request."""
    email: str
    password: str


# ============================================
# SERVICE
# ============================================

class ServiceBase(BaseSchema):
    """Base service model."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    duration_minutes: int = Field(..., ge=5, le=480)
    buffer_minutes: int = Field(default=0, ge=0, le=60)
    price: Optional[Decimal] = Field(default=None, ge=0)
    is_active: bool = Field(default=True)
    requires_approval: bool = Field(default=False)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ServiceCreate(ServiceBase):
    """Create service request."""
    business_id: UUID


class Service(ServiceBase, TimestampMixin):
    """Service model with ID."""
    id: UUID
    business_id: UUID


# ============================================
# RESOURCE
# ============================================

class ResourceBase(BaseSchema):
    """Base resource model."""
    name: str = Field(..., min_length=1, max_length=255)
    type: ResourceType
    is_active: bool = Field(default=True)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ResourceCreate(ResourceBase):
    """Create resource request."""
    business_id: UUID


class Resource(ResourceBase):
    """Resource model with ID."""
    id: UUID
    business_id: UUID


# ============================================
# WORKING HOURS
# ============================================

class WorkingHoursBase(BaseSchema):
    """Base working hours model."""
    day_of_week: int = Field(..., ge=0, le=6)  # 0=Sunday
    start_time: time
    end_time: time
    is_active: bool = Field(default=True)
    
    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v, info):
        if info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v


class WorkingHoursCreate(WorkingHoursBase):
    """Create working hours request."""
    business_id: UUID
    resource_id: Optional[UUID] = None


class WorkingHours(WorkingHoursBase):
    """Working hours model with ID."""
    id: UUID
    business_id: UUID
    resource_id: Optional[UUID] = None


# ============================================
# BOOKING
# ============================================

class BookingBase(BaseSchema):
    """Base booking model."""
    start_time: datetime
    end_time: datetime
    customer_notes: Optional[str] = None
    admin_notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v, info):
        if info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v


class BookingCreate(BookingBase):
    """Create booking request."""
    business_id: UUID
    service_id: UUID
    user_id: Optional[UUID] = None
    resource_id: Optional[UUID] = None
    source: BookingSource = Field(default=BookingSource.VOICE_AI)
    conversation_id: Optional[UUID] = None


class BookingUpdate(BaseSchema):
    """Update booking request."""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[BookingStatus] = None
    admin_notes: Optional[str] = None


class Booking(BookingBase, TimestampMixin):
    """Booking model with ID."""
    id: UUID
    business_id: UUID
    user_id: Optional[UUID] = None
    service_id: Optional[UUID] = None
    resource_id: Optional[UUID] = None
    status: BookingStatus = BookingStatus.PENDING_APPROVAL
    source: BookingSource = BookingSource.VOICE_AI
    conversation_id: Optional[UUID] = None
    approval_admin_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None


class BookingWithDetails(Booking):
    """Booking with related entities."""
    user: Optional[User] = None
    service: Optional[Service] = None
    resource: Optional[Resource] = None


# ============================================
# ORDER
# ============================================

class OrderItem(BaseSchema):
    """Order item model."""
    product_id: str
    name: str
    quantity: int = Field(..., ge=1)
    price: Decimal


class OrderBase(BaseSchema):
    """Base order model."""
    items: List[OrderItem]
    customer_notes: Optional[str] = None
    admin_notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OrderCreate(OrderBase):
    """Create order request."""
    business_id: UUID
    user_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None


class Order(OrderBase, TimestampMixin):
    """Order model with ID."""
    id: UUID
    business_id: UUID
    user_id: Optional[UUID] = None
    status: OrderStatus = OrderStatus.PENDING_APPROVAL
    total_amount: Optional[Decimal] = None
    conversation_id: Optional[UUID] = None
    approval_admin_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None


# ============================================
# SERVICE REQUEST
# ============================================

class ServiceRequestBase(BaseSchema):
    """Base service request model."""
    request_type: str = Field(..., max_length=100)
    description: Optional[str] = None
    priority: RequestPriority = RequestPriority.NORMAL
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ServiceRequestCreate(ServiceRequestBase):
    """Create service request."""
    business_id: UUID
    user_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None


class ServiceRequest(ServiceRequestBase, TimestampMixin):
    """Service request model with ID."""
    id: UUID
    business_id: UUID
    user_id: Optional[UUID] = None
    status: RequestStatus = RequestStatus.PENDING
    conversation_id: Optional[UUID] = None
    assigned_to: Optional[UUID] = None


# ============================================
# CONVERSATION
# ============================================

class ConversationTurnBase(BaseSchema):
    """Base conversation turn model."""
    turn_number: int = Field(..., ge=1)
    role: str = Field(..., max_length=20)  # user, assistant, system
    content: str
    intent: Optional[str] = Field(default=None, max_length=50)
    entities: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[Decimal] = Field(default=None, ge=0, le=1)
    audio_duration_ms: Optional[int] = None
    processing_time_ms: Optional[int] = None


class ConversationTurnCreate(ConversationTurnBase):
    """Create conversation turn request."""
    session_id: UUID


class ConversationTurn(ConversationTurnBase):
    """Conversation turn model with ID."""
    id: UUID
    session_id: UUID
    created_at: datetime


class ConversationSessionBase(BaseSchema):
    """Base conversation session model."""
    channel: ChannelType
    phone_number: Optional[str] = Field(default=None, max_length=20)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationSessionCreate(ConversationSessionBase):
    """Create conversation session request."""
    business_id: UUID
    user_id: Optional[UUID] = None


class ConversationSession(ConversationSessionBase):
    """Conversation session model with ID."""
    id: UUID
    business_id: UUID
    user_id: Optional[UUID] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    status: ConversationStatus = ConversationStatus.ACTIVE
    current_intent: Optional[str] = None
    intent_confidence: Optional[Decimal] = None
    final_outcome: Optional[str] = None
    transferred_to_human: bool = False
    transfer_reason: Optional[str] = None
    slots_collected: Dict[str, Any] = Field(default_factory=dict)
    booking_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    request_id: Optional[UUID] = None
    recording_path: Optional[str] = None


class ConversationSessionWithTurns(ConversationSession):
    """Conversation session with turns."""
    turns: List[ConversationTurn] = Field(default_factory=list)


# ============================================
# AVAILABILITY
# ============================================

class TimeSlot(BaseSchema):
    """Available time slot."""
    start: datetime
    end: datetime
    available: bool = True


class AvailabilityQuery(BaseSchema):
    """Availability query parameters."""
    business_id: UUID
    service_id: UUID
    date: str  # YYYY-MM-DD
    resource_id: Optional[UUID] = None


class AvailabilityResponse(BaseSchema):
    """Availability response."""
    date: str
    service_id: UUID
    slots: List[TimeSlot]


# ============================================
# NOTIFICATIONS
# ============================================

class NotificationLog(BaseSchema, TimestampMixin):
    """Notification log model."""
    id: UUID
    business_id: UUID
    user_id: Optional[UUID] = None
    channel: str
    recipient: str
    template: Optional[str] = None
    content: Optional[str] = None
    status: str
    external_id: Optional[str] = None
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
