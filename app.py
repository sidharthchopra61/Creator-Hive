import os
import sys
import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import (
    FastAPI, Depends, HTTPException, status, Request, Response,
    Query, Body
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from passlib.context import CryptContext
from jose import JWTError, jwt
from dotenv import load_dotenv

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean,
    DateTime, ForeignKey, Float, Table, desc, or_, and_, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session

load_dotenv()

# ==============================================================================
# 1. CONFIGURATION & LOGGING
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("CreatorHive")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./creatorhive.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY = os.getenv("SECRET_KEY", "creatorhive-production-grade-secret-key-93847293847239487")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "4320"))
PORT = int(os.getenv("PORT", "8000"))

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@creatorhive.io")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "AdminHiveSecure2026!")

# ==============================================================================
# 2. DATABASE INITIALIZATION
# ==============================================================================
def create_resilient_engine(primary_url: str):
    if "sqlite" not in primary_url:
        try:
            connect_args = {"check_same_thread": False} if "sqlite" in primary_url else {}
            test_engine = create_engine(primary_url, connect_args=connect_args, pool_pre_ping=True)
            with test_engine.connect():
                logger.info("Connected to primary PostgreSQL database engine.")
                return test_engine
        except Exception as exc:
            logger.warning(
                f"PostgreSQL driver or server offline ({exc}). "
                "Activating local SQLite engine (creatorhive.db)."
            )
            fallback_url = "sqlite:///./creatorhive.db"
            return create_engine(fallback_url, connect_args={"check_same_thread": False})
    return create_engine(primary_url, connect_args={"check_same_thread": False})

engine = create_resilient_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==============================================================================
# 3. DATABASE SCHEMA
# ==============================================================================
shortlist_items = Table(
    "shortlist_items",
    Base.metadata,
    Column("shortlist_id", Integer, ForeignKey("shortlists.id", ondelete="CASCADE"), primary_key=True),
    Column("creator_id", Integer, ForeignKey("creators.id", ondelete="CASCADE"), primary_key=True),
    Column("added_at", DateTime, default=lambda: datetime.now(timezone.utc))
)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = Column(DateTime, nullable=True)

    brand_profile = relationship("Brand", back_populates="user", uselist=False, cascade="all, delete-orphan")
    creator_profile = relationship("Creator", back_populates="user", uselist=False, cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

class Brand(Base):
    __tablename__ = "brands"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    business_name = Column(String(255), nullable=False, index=True)
    contact_person = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False, index=True)
    custom_category = Column(String(100), nullable=True)
    mobile = Column(String(50), nullable=True)
    website = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True, default="India")
    logo_url = Column(String(500), nullable=True)

    user = relationship("User", back_populates="brand_profile")
    campaigns = relationship("Campaign", back_populates="brand", cascade="all, delete-orphan")
    shortlists = relationship("Shortlist", back_populates="brand", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="brand", cascade="all, delete-orphan")
    relationship_memories = relationship("RelationshipMemory", back_populates="brand", cascade="all, delete-orphan")

class Creator(Base):
    __tablename__ = "creators"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    display_name = Column(String(255), nullable=False, index=True)
    mobile = Column(String(50), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True, default="India")
    profile_image_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)
    category = Column(String(100), nullable=True, index=True)
    niche = Column(String(100), nullable=True, index=True)
    languages = Column(String(255), nullable=True, default="English, Hindi")
    profile_completion = Column(Integer, default=30)
    availability = Column(String(50), default="Available")
    base_rate_reel = Column(Float, nullable=True)
    base_rate_post = Column(Float, nullable=True)
    base_rate_story = Column(Float, nullable=True)
    base_rate_video = Column(Float, nullable=True)

    user = relationship("User", back_populates="creator_profile")
    social_channels = relationship("SocialChannel", back_populates="creator", cascade="all, delete-orphan")
    applications = relationship("CampaignApplication", back_populates="creator", cascade="all, delete-orphan")
    profile_views = relationship("ProfileView", back_populates="creator", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="creator", cascade="all, delete-orphan")
    saved_in_shortlists = relationship("Shortlist", secondary=shortlist_items, back_populates="creators")
    reliability_metrics = relationship("CreatorReliability", back_populates="creator", uselist=False,
                                       cascade="all, delete-orphan")
    relationship_memories = relationship("RelationshipMemory", back_populates="creator", cascade="all, delete-orphan")

class SocialChannel(Base):
    __tablename__ = "social_channels"
    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(50), nullable=False, index=True)
    profile_url = Column(String(500), nullable=False)
    channel_name = Column(String(255), nullable=False)
    followers_count = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)
    is_verified_channel = Column(Boolean, default=False)
    is_manual_entry = Column(Boolean, default=True)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    creator = relationship("Creator", back_populates="social_channels")

class CreatorReliability(Base):
    __tablename__ = "creator_reliability"
    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), unique=True, nullable=False)
    response_rate = Column(Float, default=100.0)
    on_time_delivery_rate = Column(Float, default=100.0)
    campaign_completion_rate = Column(Float, default=100.0)
    approval_rate = Column(Float, default=100.0)
    total_collabs_completed = Column(Integer, default=0)

    creator = relationship("Creator", back_populates="reliability_metrics")

class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    objective = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    target_platforms = Column(String(255), nullable=False)
    creator_category = Column(String(100), nullable=True)
    niche = Column(String(100), nullable=True)
    audience_range = Column(String(100), nullable=True)
    target_location = Column(String(255), nullable=True)
    deliverables = Column(Text, nullable=False)
    budget = Column(Float, nullable=False, default=0.0)
    deadline = Column(DateTime, nullable=True)
    requirements = Column(Text, nullable=True)
    content_guidelines = Column(Text, nullable=True)
    brand_guidelines = Column(Text, nullable=True)
    status = Column(String(50), default="Published", nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    brand = relationship("Brand", back_populates="campaigns")
    applications = relationship("CampaignApplication", back_populates="campaign", cascade="all, delete-orphan")
    deliverables_records = relationship("CampaignDeliverable", back_populates="campaign", cascade="all, delete-orphan")

class CampaignApplication(Base):
    __tablename__ = "campaign_applications"
    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    proposal = Column(Text, nullable=False)
    message = Column(Text, nullable=True)
    proposed_price = Column(Float, nullable=False)
    relevant_experience = Column(Text, nullable=True)
    status = Column(String(50), default="Submitted", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    campaign = relationship("Campaign", back_populates="applications")
    creator = relationship("Creator", back_populates="applications")
    submissions = relationship("ContentSubmission", back_populates="application", cascade="all, delete-orphan")

class ContentSubmission(Base):
    __tablename__ = "content_submissions"
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("campaign_applications.id", ondelete="CASCADE"), nullable=False)
    content_url = Column(String(500), nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(String(50), default="Submitted", nullable=False)
    revision_feedback = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_at = Column(DateTime, nullable=True)

    application = relationship("CampaignApplication", back_populates="submissions")

class CampaignDeliverable(Base):
    __tablename__ = "campaign_deliverables"
    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    deliverable_name = Column(String(255), nullable=False)
    platform = Column(String(50), nullable=False)
    status = Column(String(50), default="Pending")

    campaign = relationship("Campaign", back_populates="deliverables_records")

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_message_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    brand = relationship("Brand", back_populates="conversations")
    creator = relationship("Creator", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan",
                            order_by="Message.created_at.asc()")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    sender_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    attachment_url = Column(String(500), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User")

class Shortlist(Base):
    __tablename__ = "shortlists"
    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False, default="Primary Shortlist")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    brand = relationship("Brand", back_populates="shortlists")
    creators = relationship("Creator", secondary=shortlist_items, back_populates="saved_in_shortlists")

class RelationshipMemory(Base):
    __tablename__ = "relationship_memory"
    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    notes = Column(Text, nullable=True)
    collaboration_rating = Column(Integer, default=5)
    total_campaigns_partnered = Column(Integer, default=1)
    last_collaborated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    brand = relationship("Brand", back_populates="relationship_memories")
    creator = relationship("Creator", back_populates="relationship_memories")

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)
    platform_fee = Column(Float, default=0.0)
    status = Column(String(50), default="Pending", nullable=False)
    invoice_number = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    paid_at = Column(DateTime, nullable=True)

class ProfileView(Base):
    __tablename__ = "profile_views"
    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False)
    viewer_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    creator = relationship("Creator", back_populates="profile_views")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    action_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="notifications")

Base.metadata.create_all(bind=engine)

# ==============================================================================
# 4. SECURITY & AUTH
# ==============================================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password[:72], hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password[:72])

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("creatorhive_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        return None
    return user

async def get_current_user(user: Optional[User] = Depends(get_current_user_optional)) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid.")
    return user

def require_roles(roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Unauthorized for role: {current_user.role}")
        return current_user
    return role_checker

def init_superadmin():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not existing:
            hashed = get_password_hash(ADMIN_PASSWORD)
            superadmin = User(
                email=ADMIN_EMAIL,
                hashed_password=hashed,
                role="Super Admin",
                is_active=True,
                is_verified=True,
                created_at=datetime.now(timezone.utc)
            )
            db.add(superadmin)
            db.commit()
            logger.info(f"System Super Admin initialized: {ADMIN_EMAIL}")
    except Exception as e:
        logger.error(f"Error bootstrapping administrator: {e}")
    finally:
        db.close()

init_superadmin()

# ==============================================================================
# 5. FASTAPI & SCHEMAS
# ==============================================================================
app = FastAPI(title="Creator Hive Enterprise", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CreatorRegisterSchema(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=8)
    mobile: Optional[str] = None
    city: Optional[str] = "Jammu"
    state: Optional[str] = "Jammu and Kashmir"
    country: Optional[str] = "India"
    profile_image_url: Optional[str] = None

class CreatorProfileUpdateSchema(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    category: Optional[str] = None
    niche: Optional[str] = None
    languages: Optional[str] = None
    availability: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    base_rate_reel: Optional[float] = None
    base_rate_post: Optional[float] = None
    base_rate_story: Optional[float] = None
    base_rate_video: Optional[float] = None

class SocialChannelCreateSchema(BaseModel):
    platform: str = Field(..., pattern="^(Instagram|YouTube|TikTok|Facebook|LinkedIn|X)$")
    profile_url: str = Field(..., min_length=4)
    channel_name: str = Field(..., min_length=1)
    followers_count: int = Field(default=0, ge=0)
    engagement_rate: float = Field(default=0.0, ge=0.0)

class BrandRegisterSchema(BaseModel):
    business_name: str = Field(..., min_length=2)
    contact_person: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=8)
    category: str
    custom_category: Optional[str] = None
    mobile: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    logo_url: Optional[str] = None

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class CampaignCreateSchema(BaseModel):
    title: str = Field(..., min_length=3)
    category: str
    objective: str
    description: str
    target_platforms: List[str]
    creator_category: Optional[str] = None
    niche: Optional[str] = None
    audience_range: Optional[str] = "10K–50K"
    target_location: Optional[str] = "All India"
    deliverables: str
    budget: float = Field(..., gt=0)
    deadline_days: int = Field(default=30, gt=0)
    requirements: Optional[str] = None
    content_guidelines: Optional[str] = None
    brand_guidelines: Optional[str] = None

class CampaignApplySchema(BaseModel):
    campaign_id: int
    proposal: str = Field(..., min_length=10)
    message: Optional[str] = None
    proposed_price: float = Field(..., gt=0)
    relevant_experience: Optional[str] = None

class ContentSubmissionSchema(BaseModel):
    application_id: int
    content_url: str = Field(..., min_length=5)
    notes: Optional[str] = None

class MessageSendSchema(BaseModel):
    conversation_id: int
    content: str = Field(..., min_length=1)
    attachment_url: Optional[str] = None

class ShortlistToggleSchema(BaseModel):
    shortlist_id: int
    creator_id: int

# ==============================================================================
# 6. MATCHING & COLLAB INTELLIGENCE ENGINES
# ==============================================================================
def calculate_creator_match_score(creator: Optional[Creator], campaign: Campaign) -> Dict[str, Any]:
    if not creator:
        return {"score": 75, "factors": ["General profile alignment", "Platform presence required"], "label": "Eligible"}

    score = 0
    reasons = []

    if creator.category and campaign.category:
        if creator.category.lower() == campaign.category.lower():
            score += 35
            reasons.append(f"Category verified ({creator.category})")
        elif any(word in campaign.description.lower() for word in creator.category.lower().split()):
            score += 20
            reasons.append("Relevant category overlap")

    camp_platforms = [p.strip().lower() for p in campaign.target_platforms.split(",")]
    creator_platforms = [c.platform.lower() for c in creator.social_channels]
    matched = set(camp_platforms).intersection(set(creator_platforms))
    if matched:
        pts = min(30, int((len(matched) / max(len(camp_platforms), 1)) * 30))
        score += pts
        reasons.append(f"Matching channels: {', '.join([m.title() for m in matched])}")
    else:
        reasons.append("No directly linked target channel yet")

    total_followers = sum(c.followers_count for c in creator.social_channels)
    range_map = {
        "Under 1K": (0, 1000),
        "1K–10K": (1000, 10000),
        "10K–50K": (10000, 50000),
        "50K–100K": (50000, 100000),
        "100K–500K": (100000, 500000),
        "500K–1M": (500000, 1000000),
        "1M+": (1000000, 100000000)
    }
    bounds = range_map.get(campaign.audience_range, (0, 100000000))
    if bounds[0] <= total_followers <= bounds[1]:
        score += 20
        reasons.append(f"Within audience tier ({campaign.audience_range})")
    elif total_followers > bounds[1]:
        score += 15
        reasons.append("Audience exceeds baseline requirement")

    if campaign.target_location and creator.city:
        if campaign.target_location.lower() in ["all", "all india", "remote"] or campaign.target_location.lower() in creator.city.lower():
            score += 15
            reasons.append(f"Location compatible ({creator.city})")
        elif creator.country and campaign.target_location.lower() in creator.country.lower():
            score += 10
            reasons.append(f"Country aligned ({creator.country})")

    final_score = min(score, 99)
    if final_score >= 80:
        label = "High Affinity Match"
    elif final_score >= 50:
        label = "Strong Fit"
    else:
        label = "Moderate Alignment"

    return {
        "score": final_score,
        "factors": reasons or ["Profile criteria active"],
        "label": label
    }

def calculate_collab_intelligence(creator: Creator) -> Dict[str, Any]:
    rel = creator.reliability_metrics
    if not rel or rel.total_collabs_completed == 0:
        return {
            "has_data": False,
            "response_rate": "100%",
            "on_time_rate": "100%",
            "campaign_success": "100%",
            "composite_score": 98,
            "badge": "Verified Pioneer"
        }
    composite = int((rel.response_rate * 0.3) + (rel.on_time_delivery_rate * 0.3) + (rel.approval_rate * 0.4))
    return {
        "has_data": True,
        "response_rate": f"{int(rel.response_rate)}%",
        "on_time_rate": f"{int(rel.on_time_delivery_rate)}%",
        "campaign_success": f"{int(rel.approval_rate)}%",
        "composite_score": composite,
        "badge": "Top Performer" if composite >= 90 else "Verified Talent"
    }

# ==============================================================================
# 7. REST APIS
# ==============================================================================
@app.post("/api/auth/register-creator")
def register_creator(data: CreatorRegisterSchema, response: Response, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = User(
        email=data.email.lower(),
        hashed_password=get_password_hash(data.password),
        role="Creator",
        is_active=True,
        is_verified=False,
        last_login=datetime.now(timezone.utc)
    )
    db.add(user)
    db.flush()

    creator = Creator(
        user_id=user.id,
        first_name=data.first_name,
        last_name=data.last_name,
        display_name=data.display_name,
        mobile=data.mobile,
        city=data.city,
        state=data.state,
        country=data.country or "India",
        profile_image_url=data.profile_image_url or "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=300",
        profile_completion=30
    )
    db.add(creator)
    db.flush()

    rel = CreatorReliability(creator_id=creator.id)
    db.add(rel)

    token = create_access_token({"sub": str(user.id), "role": user.role})
    response.set_cookie(key="creatorhive_token", value=token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                        samesite="lax")
    db.commit()
    return {"status": "success", "user_id": user.id, "role": user.role}

@app.post("/api/auth/register-brand")
def register_brand(data: BrandRegisterSchema, response: Response, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    category = data.custom_category.strip() if data.category == "Other" and data.custom_category else data.category

    user = User(
        email=data.email.lower(),
        hashed_password=get_password_hash(data.password),
        role="Brand",
        is_active=True,
        is_verified=False,
        last_login=datetime.now(timezone.utc)
    )
    db.add(user)
    db.flush()

    brand = Brand(
        user_id=user.id,
        business_name=data.business_name,
        contact_person=data.contact_person,
        category=category,
        custom_category=data.custom_category,
        mobile=data.mobile,
        website=data.website,
        description=data.description,
        city=data.city,
        state=data.state,
        country=data.country or "India",
        logo_url=data.logo_url or "https://images.unsplash.com/photo-1560179707-f14e90ef3623?w=150"
    )
    db.add(brand)
    db.flush()

    default_shortlist = Shortlist(brand_id=brand.id, name="Primary Shortlist", notes="Default talent roster")
    db.add(default_shortlist)

    token = create_access_token({"sub": str(user.id), "role": user.role})
    response.set_cookie(key="creatorhive_token", value=token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                        samesite="lax")
    db.commit()
    return {"status": "success", "user_id": user.id, "role": user.role}

@app.post("/api/auth/login")
def login(data: LoginSchema, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid registered email or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account has been suspended.")

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token({"sub": str(user.id), "role": user.role})
    response.set_cookie(key="creatorhive_token", value=token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                        samesite="lax")
    return {"status": "success", "user_id": user.id, "role": user.role}

@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(key="creatorhive_token")
    return {"status": "success", "message": "Session destroyed."}

@app.get("/api/auth/me")
def get_current_user_profile(user: User = Depends(get_current_user)):
    profile_data = {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "is_verified": user.is_verified,
        "created_at": user.created_at.isoformat()
    }
    if user.role == "Brand" and user.brand_profile:
        profile_data["profile"] = {
            "id": user.brand_profile.id,
            "business_name": user.brand_profile.business_name,
            "category": user.brand_profile.category,
            "logo_url": user.brand_profile.logo_url
        }
    elif user.role == "Creator" and user.creator_profile:
        c = user.creator_profile
        profile_data["profile"] = {
            "id": c.id,
            "display_name": c.display_name,
            "category": c.category or "Uncategorized",
            "profile_completion": c.profile_completion,
            "profile_image_url": c.profile_image_url
        }
    return profile_data

@app.post("/api/creator/profile/update")
def update_creator_profile(data: CreatorProfileUpdateSchema, current_user: User = Depends(require_roles(["Creator"])),
                           db: Session = Depends(get_db)):
    creator = current_user.creator_profile
    for field, value in data.dict(exclude_unset=True).items():
        if value is not None:
            setattr(creator, field, value)

    completion = 30
    if creator.bio and len(creator.bio) > 10: completion += 20
    if creator.category: completion += 20
    if len(creator.social_channels) > 0: completion += 30
    creator.profile_completion = min(completion, 100)

    db.commit()
    return {"status": "success", "profile_completion": creator.profile_completion}

@app.post("/api/creator/channels/add")
def add_social_channel(data: SocialChannelCreateSchema, current_user: User = Depends(require_roles(["Creator"])),
                       db: Session = Depends(get_db)):
    creator = current_user.creator_profile
    channel = SocialChannel(
        creator_id=creator.id,
        platform=data.platform,
        profile_url=data.profile_url,
        channel_name=data.channel_name,
        followers_count=data.followers_count,
        engagement_rate=data.engagement_rate,
        is_manual_entry=True
    )
    db.add(channel)
    db.flush()

    if creator.profile_completion < 100 and len(creator.social_channels) >= 1:
        creator.profile_completion = min(creator.profile_completion + 20, 100)

    db.commit()
    return {"status": "success", "channel_id": channel.id}

@app.delete("/api/creator/channels/{channel_id}")
def delete_social_channel(channel_id: int, current_user: User = Depends(require_roles(["Creator"])),
                          db: Session = Depends(get_db)):
    channel = db.query(SocialChannel).filter(
        SocialChannel.id == channel_id,
        SocialChannel.creator_id == current_user.creator_profile.id
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found.")
    db.delete(channel)
    db.commit()
    return {"status": "success", "message": "Channel removed."}

@app.get("/api/creators/discover")
def discover_creators(
        q: Optional[str] = None,
        category: Optional[str] = None,
        platform: Optional[str] = None,
        audience: Optional[str] = None,
        location: Optional[str] = None,
        page: int = 1,
        limit: int = 12,
        db: Session = Depends(get_db)
):
    query = db.query(Creator).join(User).filter(User.is_active == True)

    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            or_(
                Creator.display_name.ilike(search_pattern),
                Creator.bio.ilike(search_pattern),
                Creator.category.ilike(search_pattern),
                Creator.niche.ilike(search_pattern)
            )
        )
    if category and category != "All":
        query = query.filter(Creator.category.ilike(f"%{category}%"))
    if location:
        query = query.filter(
            or_(
                Creator.city.ilike(f"%{location}%"),
                Creator.state.ilike(f"%{location}%"),
                Creator.country.ilike(f"%{location}%")
            )
        )
    if platform and platform != "All":
        query = query.join(SocialChannel).filter(SocialChannel.platform.ilike(platform))

    creators = query.distinct().all()

    results = []
    for c in creators:
        total_followers = sum(sc.followers_count for sc in c.social_channels)
        avg_eng = (sum(sc.engagement_rate for sc in c.social_channels) / len(
            c.social_channels)) if c.social_channels else 2.8

        if audience and audience != "All":
            range_map = {
                "Under 1K": (0, 1000), "1K–10K": (1000, 10000), "10K–50K": (10000, 50000),
                "50K–100K": (50000, 100000), "100K–500K": (100000, 500000), "1M+": (1000000, 100000000)
            }
            if audience in range_map:
                low, high = range_map[audience]
                if not (low <= total_followers <= high):
                    continue

        rel = calculate_collab_intelligence(c)
        results.append({
            "id": c.id,
            "name": c.display_name,
            "category": c.category or "Talent",
            "niche": c.niche or "Lifestyle & Media",
            "city": c.city or "Jammu",
            "country": c.country or "India",
            "bio": c.bio or "Verified Creator on Creator Hive ecosystem.",
            "profile_image_url": c.profile_image_url or "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=300",
            "total_followers": total_followers,
            "average_engagement_rate": round(avg_eng, 2),
            "is_verified": c.user.is_verified,
            "collab_score": rel["composite_score"],
            "collab_badge": rel["badge"],
            "platforms": [{"platform": sc.platform, "followers": sc.followers_count, "engagement": sc.engagement_rate} for sc in c.social_channels]
        })

    paginated = results[(page - 1) * limit : page * limit]
    return {
        "creators": paginated,
        "pagination": {"total": len(results), "page": page, "limit": limit}
    }

@app.get("/api/creators/{creator_id}")
def get_creator_profile(creator_id: int, current_user: Optional[User] = Depends(get_current_user_optional),
                        db: Session = Depends(get_db)):
    creator = db.query(Creator).filter(Creator.id == creator_id).first()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found.")

    db.add(ProfileView(creator_id=creator.id, viewer_user_id=current_user.id if current_user else None))
    db.commit()

    channels = [{
        "id": sc.id,
        "platform": sc.platform,
        "channel_name": sc.channel_name,
        "profile_url": sc.profile_url,
        "followers": sc.followers_count,
        "engagement_rate": sc.engagement_rate
    } for sc in creator.social_channels]

    collab_score = calculate_collab_intelligence(creator)
    total_followers = sum(sc.followers_count for sc in creator.social_channels)

    return {
        "id": creator.id,
        "name": creator.display_name,
        "first_name": creator.first_name,
        "last_name": creator.last_name,
        "category": creator.category or "General Talent",
        "niche": creator.niche or "Content Creation",
        "bio": creator.bio or "Content creator specializing in high-engagement audience storytelling.",
        "city": creator.city or "Jammu",
        "state": creator.state or "Jammu and Kashmir",
        "country": creator.country or "India",
        "languages": creator.languages or "English, Hindi",
        "profile_image_url": creator.profile_image_url,
        "total_followers": total_followers,
        "is_verified": creator.user.is_verified,
        "availability": creator.availability or "Available",
        "social_channels": channels,
        "rates": {
            "reel": creator.base_rate_reel or 15000,
            "post": creator.base_rate_post or 10000,
            "story": creator.base_rate_story or 5000,
            "video": creator.base_rate_video or 35000
        },
        "collab_intelligence": collab_score,
        "member_since": creator.user.created_at.strftime("%B %Y")
    }

@app.post("/api/campaigns/create")
def create_campaign(data: CampaignCreateSchema, current_user: User = Depends(require_roles(["Brand"])),
                    db: Session = Depends(get_db)):
    brand = current_user.brand_profile
    deadline_date = datetime.now(timezone.utc) + timedelta(days=data.deadline_days)
    campaign = Campaign(
        brand_id=brand.id,
        title=data.title,
        category=data.category,
        objective=data.objective,
        description=data.description,
        target_platforms=",".join(data.target_platforms),
        creator_category=data.creator_category,
        niche=data.niche,
        audience_range=data.audience_range,
        target_location=data.target_location,
        deliverables=data.deliverables,
        budget=data.budget,
        deadline=deadline_date,
        requirements=data.requirements,
        content_guidelines=data.content_guidelines,
        brand_guidelines=data.brand_guidelines,
        status="Published"
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return {"status": "success", "campaign_id": campaign.id}

@app.get("/api/campaigns/opportunities")
def browse_campaigns(current_user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    campaigns = db.query(Campaign).filter(Campaign.status == "Published").order_by(desc(Campaign.created_at)).all()
    results = []
    creator_profile = current_user.creator_profile if (current_user and current_user.role == "Creator") else None

    for c in campaigns:
        match_info = calculate_creator_match_score(creator_profile, c)
        results.append({
            "id": c.id,
            "title": c.title,
            "brand_name": c.brand.business_name,
            "category": c.category,
            "objective": c.objective,
            "description": c.description,
            "platforms": c.target_platforms.split(","),
            "location": c.target_location or "All India",
            "budget": c.budget,
            "deadline": c.deadline.strftime("%d %b %Y") if c.deadline else "Ongoing",
            "deliverables": c.deliverables,
            "requirements": c.requirements,
            "match": match_info
        })
    return {"campaigns": results}

@app.post("/api/campaigns/apply")
def apply_to_campaign(data: CampaignApplySchema, current_user: User = Depends(require_roles(["Creator"])),
                      db: Session = Depends(get_db)):
    creator = current_user.creator_profile
    campaign = db.query(Campaign).filter(Campaign.id == data.campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign brief not found.")

    existing = db.query(CampaignApplication).filter(
        CampaignApplication.campaign_id == campaign.id,
        CampaignApplication.creator_id == creator.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="You have already submitted a proposal for this campaign.")

    app_record = CampaignApplication(
        campaign_id=campaign.id,
        creator_id=creator.id,
        proposal=data.proposal,
        message=data.message,
        proposed_price=data.proposed_price,
        relevant_experience=data.relevant_experience,
        status="Submitted"
    )
    db.add(app_record)

    db.add(Notification(
        user_id=campaign.brand.user_id,
        title="New Campaign Proposal",
        content=f"{creator.display_name} applied to '{campaign.title}' (Quote: ₹{data.proposed_price:,.0f})."
    ))
    db.commit()
    return {"status": "success", "application_id": app_record.id}

@app.post("/api/campaigns/application/status")
def update_application_status(
        app_id: int = Body(...),
        status_value: str = Body(...),
        current_user: User = Depends(require_roles(["Brand"])),
        db: Session = Depends(get_db)
):
    application = db.query(CampaignApplication).join(Campaign).filter(
        CampaignApplication.id == app_id,
        Campaign.brand_id == current_user.brand_profile.id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found.")

    application.status = status_value

    if status_value == "Accepted":
        mem = db.query(RelationshipMemory).filter(
            RelationshipMemory.brand_id == current_user.brand_profile.id,
            RelationshipMemory.creator_id == application.creator_id
        ).first()
        if not mem:
            mem = RelationshipMemory(
                brand_id=current_user.brand_profile.id,
                creator_id=application.creator_id,
                notes=f"Accepted onto brief: {application.campaign.title}"
            )
            db.add(mem)
        else:
            mem.total_campaigns_partnered += 1
            mem.last_collaborated_at = datetime.now(timezone.utc)

    db.add(Notification(
        user_id=application.creator.user_id,
        title=f"Proposal {status_value}",
        content=f"Your pitch for '{application.campaign.title}' has been marked as {status_value}."
    ))
    db.commit()
    return {"status": "success", "new_status": status_value}

@app.post("/api/campaigns/content/submit")
def submit_content(data: ContentSubmissionSchema, current_user: User = Depends(require_roles(["Creator"])),
                   db: Session = Depends(get_db)):
    application = db.query(CampaignApplication).filter(
        CampaignApplication.id == data.application_id,
        CampaignApplication.creator_id == current_user.creator_profile.id
    ).first()
    if not application or application.status != "Accepted":
        raise HTTPException(status_code=400, detail="Cannot submit deliverables for an unaccepted brief.")

    submission = ContentSubmission(
        application_id=application.id,
        content_url=data.content_url,
        notes=data.notes,
        status="Submitted"
    )
    db.add(submission)
    db.commit()
    return {"status": "success", "submission_id": submission.id}

@app.post("/api/chat/initiate")
def initiate_chat(
        creator_id: int = Body(...),
        current_user: User = Depends(require_roles(["Brand"])),
        db: Session = Depends(get_db)
):
    brand = current_user.brand_profile
    conversation = db.query(Conversation).filter(
        Conversation.brand_id == brand.id,
        Conversation.creator_id == creator_id
    ).first()

    if not conversation:
        conversation = Conversation(
            brand_id=brand.id,
            creator_id=creator_id,
            last_message_at=datetime.now(timezone.utc)
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    return {"status": "success", "conversation_id": conversation.id}

@app.get("/api/chat/conversations")
def get_conversations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == "Brand":
        convos = db.query(Conversation).filter(Conversation.brand_id == current_user.brand_profile.id).order_by(
            desc(Conversation.last_message_at)).all()
    elif current_user.role == "Creator":
        convos = db.query(Conversation).filter(Conversation.creator_id == current_user.creator_profile.id).order_by(
            desc(Conversation.last_message_at)).all()
    else:
        return {"conversations": []}

    results = []
    for c in convos:
        last_msg = c.messages[-1] if c.messages else None
        unread_count = sum(1 for m in c.messages if not m.is_read and m.sender_user_id != current_user.id)
        other_name = c.creator.display_name if current_user.role == "Brand" else c.brand.business_name
        other_img = c.creator.profile_image_url if current_user.role == "Brand" else c.brand.logo_url
        results.append({
            "id": c.id,
            "name": other_name,
            "avatar": other_img,
            "unread_count": unread_count,
            "last_message": last_msg.content if last_msg else "Channel initialized",
            "last_message_time": last_msg.created_at.strftime("%I:%M %p") if last_msg else c.created_at.strftime("%d %b")
        })
    return {"conversations": results}

@app.get("/api/chat/{conversation_id}/messages")
def get_messages(conversation_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    convo = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    if current_user.role == "Brand" and convo.brand_id != current_user.brand_profile.id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    if current_user.role == "Creator" and convo.creator_id != current_user.creator_profile.id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")

    for m in convo.messages:
        if m.sender_user_id != current_user.id and not m.is_read:
            m.is_read = True
    db.commit()

    return {"messages": [{
        "id": m.id,
        "is_me": m.sender_user_id == current_user.id,
        "content": m.content,
        "attachment_url": m.attachment_url,
        "time": m.created_at.strftime("%I:%M %p")
    } for m in convo.messages]}

@app.post("/api/chat/send")
def send_message(data: MessageSendSchema, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    convo = db.query(Conversation).filter(Conversation.id == data.conversation_id).first()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    msg = Message(
        conversation_id=convo.id,
        sender_user_id=current_user.id,
        content=data.content,
        attachment_url=data.attachment_url
    )
    convo.last_message_at = datetime.now(timezone.utc)
    db.add(msg)
    db.commit()
    return {"status": "success", "message_id": msg.id}

@app.get("/api/brand/shortlists")
def get_brand_shortlists(current_user: User = Depends(require_roles(["Brand"])), db: Session = Depends(get_db)):
    shortlists = db.query(Shortlist).filter(Shortlist.brand_id == current_user.brand_profile.id).all()
    return {"shortlists": [{
        "id": sl.id,
        "name": sl.name,
        "notes": sl.notes,
        "count": len(sl.creators),
        "creators": [{
            "id": c.id,
            "name": c.display_name,
            "category": c.category or "Talent",
            "profile_image_url": c.profile_image_url
        } for c in sl.creators]
    } for sl in shortlists]}

@app.post("/api/brand/shortlists/toggle")
def toggle_shortlist_creator(data: ShortlistToggleSchema, current_user: User = Depends(require_roles(["Brand"])),
                             db: Session = Depends(get_db)):
    shortlist = db.query(Shortlist).filter(
        Shortlist.id == data.shortlist_id,
        Shortlist.brand_id == current_user.brand_profile.id
    ).first()
    creator = db.query(Creator).filter(Creator.id == data.creator_id).first()
    if not shortlist or not creator:
        raise HTTPException(status_code=404, detail="Entity not found.")

    if creator in shortlist.creators:
        shortlist.creators.remove(creator)
        action = "removed"
    else:
        shortlist.creators.append(creator)
        action = "added"
    db.commit()
    return {"status": "success", "action": action}

@app.get("/api/notifications")
def get_notifications(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    notes = db.query(Notification).filter(Notification.user_id == current_user.id).order_by(desc(Notification.created_at)).limit(10).all()
    return {"notifications": [{
        "id": n.id,
        "title": n.title,
        "content": n.content,
        "is_read": n.is_read,
        "created_at": n.created_at.strftime("%d %b, %I:%M %p")
    } for n in notes]}

@app.get("/api/dashboard/brand")
def get_brand_dashboard(current_user: User = Depends(require_roles(["Brand"])), db: Session = Depends(get_db)):
    brand = current_user.brand_profile
    campaigns = db.query(Campaign).filter(Campaign.brand_id == brand.id).order_by(desc(Campaign.created_at)).all()
    apps_count = db.query(CampaignApplication).join(Campaign).filter(Campaign.brand_id == brand.id).count()
    shortlists_count = sum(len(s.creators) for s in brand.shortlists)
    convos_count = db.query(Conversation).filter(Conversation.brand_id == brand.id).count()

    return {
        "metrics": {
            "active_campaigns": len(campaigns),
            "total_applications": apps_count,
            "shortlisted_creators": shortlists_count,
            "conversations": convos_count
        },
        "campaigns": [{
            "id": c.id,
            "title": c.title,
            "budget": c.budget,
            "status": c.status,
            "applications_count": len(c.applications),
            "applications": [{
                "id": a.id,
                "creator_id": a.creator_id,
                "creator_name": a.creator.display_name,
                "creator_img": a.creator.profile_image_url,
                "proposed_price": a.proposed_price,
                "proposal": a.proposal,
                "status": a.status,
                "created_at": a.created_at.strftime("%d %b %Y")
            } for a in c.applications]
        } for c in campaigns]
    }

@app.get("/api/dashboard/creator")
def get_creator_dashboard(current_user: User = Depends(require_roles(["Creator"])), db: Session = Depends(get_db)):
    creator = current_user.creator_profile
    views_count = db.query(ProfileView).filter(ProfileView.creator_id == creator.id).count()
    apps = db.query(CampaignApplication).filter(CampaignApplication.creator_id == creator.id).order_by(desc(CampaignApplication.created_at)).all()
    convos_count = db.query(Conversation).filter(Conversation.creator_id == creator.id).count()
    total_audience = sum(sc.followers_count for sc in creator.social_channels)

    return {
        "metrics": {
            "profile_completion": creator.profile_completion,
            "profile_views": views_count,
            "total_audience": total_audience,
            "applications_submitted": len(apps),
            "active_collaborations": sum(1 for a in apps if a.status == "Accepted"),
            "conversations": convos_count
        },
        "channels": [{
            "id": sc.id,
            "platform": sc.platform,
            "channel_name": sc.channel_name,
            "followers": sc.followers_count,
            "engagement": sc.engagement_rate
        } for sc in creator.social_channels],
        "applications": [{
            "id": a.id,
            "campaign_id": a.campaign.id,
            "campaign_title": a.campaign.title,
            "brand_name": a.campaign.brand.business_name,
            "quote": a.proposed_price,
            "status": a.status,
            "created_at": a.created_at.strftime("%d %b %Y")
        } for a in apps]
    }

# ==============================================================================
# 8. EMBEDDED SPA (CREATOR.CO POLISH & ARCHITECTURE)
# ==============================================================================
MASTER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Creator Hive — Modern Creator Discovery & Campaign Automation Platform</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #07090E;
      --bg-surface: #0E131F;
      --bg-elevated: #161F33;
      --bg-card: rgba(18, 26, 44, 0.7);
      --accent-primary: #2563EB;
      --accent-hover: #1D4ED8;
      --accent-glow: rgba(37, 99, 235, 0.28);
      --accent-cyan: #06B6D4;
      --text-main: #F8FAFC;
      --text-muted: #94A3B8;
      --text-dim: #64748B;
      --border-subtle: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(37, 99, 235, 0.5);
      --border-card: rgba(255, 255, 255, 0.06);
      --success: #10B981;
      --danger: #EF4444;
      --warning: #F59E0B;
      --radius-sm: 8px;
      --radius-md: 12px;
      --radius-lg: 18px;
      --radius-pill: 9999px;
      --glass-blur: blur(20px);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', -apple-system, sans-serif; }
    html { scroll-behavior: smooth; }
    body { background-color: var(--bg-base); color: var(--text-main); min-height: 100vh; overflow-x: hidden; line-height: 1.5; }
    a { color: inherit; text-decoration: none; }
    button, input, select, textarea { font-family: inherit; }

    .container { max-width: 1240px; margin: 0 auto; padding: 0 28px; }
    .flex { display: flex; }
    .items-center { align-items: center; }
    .justify-between { justify-content: space-between; }
    .justify-center { justify-content: center; }
    .gap-1 { gap: 4px; }
    .gap-2 { gap: 8px; }
    .gap-3 { gap: 12px; }
    .gap-4 { gap: 16px; }
    .gap-6 { gap: 24px; }
    .gap-8 { gap: 32px; }
    .grid { display: grid; }
    .grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .grid-cols-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .hidden { display: none !important; }

    /* BUTTONS & UI PRIMITIVES */
    .btn {
      padding: 10px 22px; border-radius: var(--radius-sm); font-size: 14px; font-weight: 600; cursor: pointer;
      display: inline-flex; align-items: center; justify-content: center; gap: 8px; transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
      border: 1px solid transparent; text-decoration: none;
    }
    .btn-primary { background: linear-gradient(135deg, var(--accent-primary), #1D4ED8); color: #fff; box-shadow: 0 4px 20px var(--accent-glow); }
    .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 24px rgba(37, 99, 235, 0.45); }
    .btn-outline { background: rgba(255, 255, 255, 0.03); border-color: var(--border-subtle); color: var(--text-main); }
    .btn-outline:hover { background: rgba(255, 255, 255, 0.08); border-color: var(--border-focus); transform: translateY(-1px); }
    .btn-sm { padding: 6px 14px; font-size: 13px; border-radius: 6px; }
    .btn-danger { background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.3); color: #FCA5A5; }
    .btn-danger:hover { background: rgba(239, 68, 68, 0.3); }

    .card { background: var(--bg-card); backdrop-filter: var(--glass-blur); border: 1px solid var(--border-card); border-radius: var(--radius-md); padding: 24px; transition: border-color 0.2s ease, transform 0.2s ease; }
    .card-hover:hover { border-color: rgba(37, 99, 235, 0.35); transform: translateY(-3px); }
    .badge { padding: 4px 10px; border-radius: var(--radius-pill); font-size: 11px; font-weight: 600; letter-spacing: 0.3px; text-transform: uppercase; display: inline-flex; align-items: center; gap: 5px; }
    .badge-primary { background: rgba(37, 99, 235, 0.15); color: #93C5FD; border: 1px solid rgba(37, 99, 235, 0.3); }
    .badge-verified { background: rgba(16, 185, 129, 0.12); color: #6EE7B7; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-cyan { background: rgba(6, 182, 212, 0.12); color: #67E8F9; border: 1px solid rgba(6, 182, 212, 0.3); }
    .badge-warning { background: rgba(245, 158, 11, 0.12); color: #FCD34D; border: 1px solid rgba(245, 158, 11, 0.3); }

    /* HEADER & NAV */
    header.site-nav {
      position: sticky; top: 0; z-index: 1000;
      background: rgba(7, 9, 14, 0.85); backdrop-filter: var(--glass-blur);
      border-bottom: 1px solid var(--border-subtle); height: 72px; display: flex; align-items: center;
    }
    .brand-logo { font-size: 20px; font-weight: 800; display: flex; align-items: center; gap: 10px; cursor: pointer; letter-spacing: -0.5px; }
    .brand-logo .logo-cube { width: 28px; height: 28px; background: linear-gradient(135deg, #2563EB, #06B6D4); border-radius: 6px; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 14px; font-weight: 800; }
    .nav-links { display: flex; gap: 32px; font-size: 14px; font-weight: 500; color: var(--text-muted); }
    .nav-links a:hover { color: #fff; }

    /* LANDING PAGE EDITORIAL DESIGN */
    .hero-section {
      padding: 110px 0 90px; position: relative; overflow: hidden;
      background: radial-gradient(circle at 50% 0%, rgba(37, 99, 235, 0.22) 0%, transparent 65%);
      border-bottom: 1px solid var(--border-subtle); text-align: center;
    }
    .hero-pill {
      display: inline-flex; align-items: center; gap: 8px; padding: 6px 18px; border-radius: var(--radius-pill);
      background: rgba(37, 99, 235, 0.1); border: 1px solid rgba(37, 99, 235, 0.3); color: #93C5FD;
      font-size: 13px; font-weight: 600; margin-bottom: 28px;
    }
    .hero-title { font-size: 64px; font-weight: 800; line-height: 1.08; letter-spacing: -2.5px; margin-bottom: 24px; max-width: 900px; margin-left: auto; margin-right: auto; }
    .hero-title span { background: linear-gradient(135deg, #FFFFFF 30%, #93C5FD 75%, #06B6D4 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .hero-desc { font-size: 19px; color: var(--text-muted); max-width: 720px; margin: 0 auto 40px; line-height: 1.6; }
    .hero-cta-group { display: flex; align-items: center; justify-content: center; gap: 16px; margin-bottom: 60px; flex-wrap: wrap; }

    .preview-container { max-width: 1060px; margin: 0 auto; border-radius: var(--radius-lg); border: 1px solid rgba(255, 255, 255, 0.12); overflow: hidden; box-shadow: 0 30px 60px -15px rgba(0,0,0,0.8); background: var(--bg-surface); }
    .preview-bar { background: #0A0E18; height: 38px; border-bottom: 1px solid var(--border-subtle); display: flex; align-items: center; padding: 0 16px; gap: 8px; }
    .preview-dot { width: 10px; height: 10px; border-radius: 50%; background: rgba(255, 255, 255, 0.15); }
    .preview-body { padding: 24px; display: grid; grid-template-columns: 240px 1fr; gap: 20px; text-align: left; }

    .section-wrap { padding: 100px 0; border-bottom: 1px solid var(--border-subtle); }
    .section-header { text-align: center; max-width: 760px; margin: 0 auto 60px; }
    .section-label { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: var(--accent-cyan); margin-bottom: 14px; }
    .section-heading { font-size: 38px; font-weight: 800; letter-spacing: -1.2px; line-height: 1.2; margin-bottom: 18px; }
    .section-subtext { font-size: 16px; color: var(--text-muted); line-height: 1.6; }

    /* WORKSPACE APP SHELL */
    .dashboard-layout { display: flex; min-height: calc(100vh - 72px); background: var(--bg-base); }
    .sidebar { width: 280px; background: var(--bg-surface); border-right: 1px solid var(--border-subtle); padding: 24px 16px; flex-shrink: 0; display: flex; flex-direction: column; justify-content: space-between; }
    .sidebar-menu { display: flex; flex-direction: column; gap: 6px; list-style: none; }
    .sidebar-link { padding: 11px 16px; border-radius: var(--radius-sm); font-size: 14px; font-weight: 600; color: var(--text-muted); display: flex; align-items: center; justify-content: space-between; cursor: pointer; transition: all 0.18s ease; }
    .sidebar-link:hover, .sidebar-link.active { background: var(--bg-elevated); color: var(--text-main); }
    .sidebar-link.active { border-left: 3px solid var(--accent-primary); }
    .main-viewport { flex: 1; padding: 40px 48px; background: var(--bg-base); overflow-y: auto; }

    /* FORMS & CONTROLS */
    .form-group { margin-bottom: 20px; }
    .form-group label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--text-muted); }
    .input-field, .select-field, .textarea-field {
      width: 100%; padding: 11px 16px; background: var(--bg-elevated); border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm); color: var(--text-main); font-size: 14px; outline: none; transition: border-color 0.2s ease;
    }
    .input-field:focus, .select-field:focus, .textarea-field:focus { border-color: var(--accent-primary); box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.2); }

    /* MODAL */
    .modal-backdrop { position: fixed; inset: 0; background: rgba(5, 7, 12, 0.85); backdrop-filter: blur(10px); z-index: 2000; display: flex; align-items: center; justify-content: center; padding: 20px; }
    .modal-box { background: var(--bg-surface); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: var(--radius-lg); width: 100%; max-width: 540px; padding: 36px; box-shadow: 0 30px 60px -15px rgba(0,0,0,0.8); max-height: 90vh; overflow-y: auto; }

    /* CHAT SUITE */
    .chat-container { display: flex; height: 680px; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; background: var(--bg-surface); }
    .chat-threads { width: 320px; border-right: 1px solid var(--border-subtle); overflow-y: auto; background: rgba(14, 19, 31, 0.7); }
    .thread-item { padding: 16px 20px; border-bottom: 1px solid var(--border-subtle); cursor: pointer; transition: background 0.15s ease; }
    .thread-item:hover, .thread-item.active { background: var(--bg-elevated); }
    .chat-stage { flex: 1; display: flex; flex-direction: column; background: var(--bg-base); }
    .chat-messages { flex: 1; padding: 24px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }
    .chat-bubble { max-width: 70%; padding: 12px 18px; border-radius: 12px; font-size: 14px; line-height: 1.5; }
    .chat-bubble.mine { align-self: flex-end; background: var(--accent-primary); color: #fff; border-bottom-right-radius: 2px; }
    .chat-bubble.theirs { align-self: flex-start; background: var(--bg-elevated); border: 1px solid var(--border-subtle); border-bottom-left-radius: 2px; }

    /* FAQ ACCORDION */
    .faq-item { border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); margin-bottom: 12px; background: var(--bg-surface); overflow: hidden; }
    .faq-trigger { padding: 20px 24px; font-weight: 700; font-size: 16px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
    .faq-answer { padding: 0 24px 20px; font-size: 14px; color: var(--text-muted); line-height: 1.6; display: none; }
    .faq-item.active .faq-answer { display: block; }
    .faq-item.active .faq-icon { transform: rotate(45deg); }
    .faq-icon { transition: transform 0.2s ease; font-size: 22px; color: var(--accent-cyan); }

    /* NOTIFICATION DROPDOWN */
    .notify-btn { position: relative; background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 18px; padding: 6px; }
    .notify-badge { position: absolute; top: 0; right: 0; width: 8px; height: 8px; background: var(--accent-cyan); border-radius: 50%; }

    @media (max-width: 900px) {
      .hero-title { font-size: 40px; letter-spacing: -1.5px; }
      .grid-cols-2, .grid-cols-3, .grid-cols-4 { grid-template-columns: 1fr; }
      .dashboard-layout { flex-direction: column; }
      .sidebar { width: 100%; border-right: none; border-bottom: 1px solid var(--border-subtle); }
      .main-viewport { padding: 24px 20px; }
      .chat-container { flex-direction: column; height: 750px; }
      .chat-threads { width: 100%; height: 200px; }
      .preview-body { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div id="app-root">
    <header class="site-nav">
      <div class="container flex items-center justify-between" style="width: 100%;">
        <div class="brand-logo" onclick="Router.navigate('/')">
          <div class="logo-cube">H</div>
          <span>CREATOR HIVE</span>
        </div>
        <nav class="nav-links">
          <a href="#/discover">Creator Discovery</a>
          <a href="#/opportunities">Campaigns</a>
          <a href="#intelligence-section" onclick="if(window.location.hash !== '') { Router.navigate('/'); setTimeout(() => document.getElementById('intelligence-section')?.scrollIntoView(), 100); }">Hive Intelligence</a>
          <a href="#leadership-section" onclick="if(window.location.hash !== '') { Router.navigate('/'); setTimeout(() => document.getElementById('leadership-section')?.scrollIntoView(), 100); }">Leadership</a>
        </nav>
        <div class="flex items-center gap-3" id="nav-actions">
          <button class="btn btn-outline btn-sm" onclick="App.openLoginModal()">Login</button>
          <button class="btn btn-primary btn-sm" onclick="App.openGetStartedModal()">Get Started</button>
        </div>
      </div>
    </header>
    <main id="main-content"></main>
  </div>

  <div id="modal-container" class="modal-backdrop hidden" onclick="if(event.target === this) App.closeModal()"></div>

  <script>
    const State = {
      user: null,
      activeConvoId: null,
      discoveryFilters: { q: '', category: 'All', platform: 'All', audience: 'All', location: '' }
    };

    const API = {
      async get(url) {
        const res = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Request failed');
        return res.json();
      },
      async post(url, data) {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Request failed');
        return res.json();
      },
      async delete(url) {
        const res = await fetch(url, { method: 'DELETE' });
        if (!res.ok) throw new Error('Deletion failed.');
        return res.json();
      }
    };

    const App = {
      async init() {
        try {
          State.user = await API.get('/api/auth/me');
          this.renderNav();
        } catch {
          State.user = null;
          this.renderNav();
        }
        Router.route();
      },

      renderNav() {
        const actions = document.getElementById('nav-actions');
        if (State.user) {
          actions.innerHTML = `
            <span style="font-size: 13px; color: var(--text-muted);">${State.user.email} (${State.user.role})</span>
            <button class="btn btn-primary btn-sm" onclick="Router.navigate('/dashboard')">Dashboard</button>
            <button class="btn btn-outline btn-sm" onclick="App.logout()">Logout</button>
          `;
        } else {
          actions.innerHTML = `
            <button class="btn btn-outline btn-sm" onclick="App.openLoginModal()">Login</button>
            <button class="btn btn-primary btn-sm" onclick="App.openGetStartedModal()">Get Started</button>
          `;
        }
      },

      async logout() {
        await API.post('/api/auth/logout', {});
        State.user = null;
        this.renderNav();
        Router.navigate('/');
      },

      openModal(html) {
        const c = document.getElementById('modal-container');
        c.innerHTML = `<div class="modal-box">${html}</div>`;
        c.classList.remove('hidden');
      },

      closeModal() {
        document.getElementById('modal-container').classList.add('hidden');
      },

      openGetStartedModal() {
        this.openModal(`
          <h2 style="font-size: 24px; font-weight: 800; margin-bottom: 6px;">Join Creator Hive</h2>
          <p style="font-size: 14px; color: var(--text-muted); margin-bottom: 24px;">Select how you want to use the platform.</p>
          <div style="display: flex; flex-direction: column; gap: 14px;">
            <div class="card card-hover" style="cursor: pointer; padding: 20px;" onclick="App.openRegisterCreatorModal()">
              <div class="flex items-center justify-between">
                <div>
                  <strong style="font-size: 16px; color: #fff;">Join as Creator</strong>
                  <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">Frictionless registration. Configure your media kit and social links inside.</div>
                </div>
                <span style="font-size: 20px; color: var(--accent-cyan);">&rarr;</span>
              </div>
            </div>
            <div class="card card-hover" style="cursor: pointer; padding: 20px;" onclick="App.openRegisterBrandModal()">
              <div class="flex items-center justify-between">
                <div>
                  <strong style="font-size: 16px; color: #fff;">Join as Brand</strong>
                  <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">Recruit creators, publish campaign briefs, and track relationship history.</div>
                </div>
                <span style="font-size: 20px; color: var(--accent-cyan);">&rarr;</span>
              </div>
            </div>
          </div>
          <button class="btn btn-outline btn-sm" style="margin-top: 20px; width: 100%;" onclick="App.closeModal()">Dismiss</button>
        `);
      },

      openLoginModal() {
        this.openModal(`
          <h2 style="font-size: 22px; font-weight: 800; margin-bottom: 6px;">Welcome Back</h2>
          <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 20px;">Access your Creator Hive workspace.</p>
          <form onsubmit="App.handleLogin(event)">
            <div class="form-group"><label>Corporate or Creator Email</label><input type="email" id="l-email" class="input-field" required /></div>
            <div class="form-group"><label>Password</label><input type="password" id="l-pass" class="input-field" required /></div>
            <div id="l-err" style="color: var(--danger); font-size: 13px; margin-bottom: 12px;"></div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">Sign In</button>
            <button type="button" class="btn btn-outline btn-sm" style="margin-top: 10px; width: 100%;" onclick="App.closeModal()">Cancel</button>
          </form>
        `);
      },

      async handleLogin(e) {
        e.preventDefault();
        try {
          await API.post('/api/auth/login', {
            email: document.getElementById('l-email').value,
            password: document.getElementById('l-pass').value
          });
          State.user = await API.get('/api/auth/me');
          App.renderNav();
          App.closeModal();
          Router.navigate('/dashboard');
        } catch (err) {
          document.getElementById('l-err').innerText = err.message;
        }
      },

      openRegisterCreatorModal() {
        this.openModal(`
          <h2 style="font-size: 22px; font-weight: 800; margin-bottom: 4px;">Create Creator Account</h2>
          <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 20px;">No channels or categories required during sign-up.</p>
          <form onsubmit="App.handleRegisterCreator(event)">
            <div class="grid grid-cols-2 gap-3">
              <div class="form-group"><label>First Name *</label><input type="text" id="rc-fn" class="input-field" required placeholder="Aman" /></div>
              <div class="form-group"><label>Last Name *</label><input type="text" id="rc-ln" class="input-field" required placeholder="Verma" /></div>
            </div>
            <div class="form-group"><label>Display Name *</label><input type="text" id="rc-dn" class="input-field" required placeholder="Aman Verma Official" /></div>
            <div class="form-group"><label>Email *</label><input type="email" id="rc-email" class="input-field" required placeholder="aman@creator.io" /></div>
            <div class="form-group"><label>Password (min 8 chars) *</label><input type="password" id="rc-pass" class="input-field" minlength="8" required placeholder="••••••••" /></div>
            <div class="grid grid-cols-2 gap-3">
              <div class="form-group"><label>Mobile</label><input type="text" id="rc-mob" class="input-field" placeholder="+91 98765 43210" /></div>
              <div class="form-group"><label>City</label><input type="text" id="rc-city" class="input-field" placeholder="Jammu" /></div>
            </div>
            <div id="rc-err" style="color: var(--danger); font-size: 13px; margin-bottom: 12px;"></div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">Create Account</button>
            <button type="button" class="btn btn-outline btn-sm" style="margin-top: 10px; width: 100%;" onclick="App.closeModal()">Back</button>
          </form>
        `);
      },

      async handleRegisterCreator(e) {
        e.preventDefault();
        try {
          await API.post('/api/auth/register-creator', {
            first_name: document.getElementById('rc-fn').value,
            last_name: document.getElementById('rc-ln').value,
            display_name: document.getElementById('rc-dn').value,
            email: document.getElementById('rc-email').value,
            password: document.getElementById('rc-pass').value,
            mobile: document.getElementById('rc-mob').value || null,
            city: document.getElementById('rc-city').value || 'Jammu'
          });
          State.user = await API.get('/api/auth/me');
          App.renderNav();
          App.closeModal();
          Router.navigate('/dashboard');
        } catch (err) {
          document.getElementById('rc-err').innerText = err.message;
        }
      },

      openRegisterBrandModal() {
        this.openModal(`
          <h2 style="font-size: 22px; font-weight: 800; margin-bottom: 6px;">Register Brand Workspace</h2>
          <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 20px;">Launch campaigns & discover vetted talent.</p>
          <form onsubmit="App.handleRegisterBrand(event)">
            <div class="form-group"><label>Business / Brand Name *</label><input type="text" id="rb-biz" class="input-field" required placeholder="Acme Tech India" /></div>
            <div class="form-group"><label>Contact Person *</label><input type="text" id="rb-contact" class="input-field" required placeholder="Rahul Sharma" /></div>
            <div class="form-group"><label>Work Email *</label><input type="email" id="rb-email" class="input-field" required placeholder="marketing@acme.com" /></div>
            <div class="form-group"><label>Password (min 8 chars) *</label><input type="password" id="rb-pass" class="input-field" minlength="8" required placeholder="••••••••" /></div>
            <div class="form-group"><label>Industry Category *</label>
              <select id="rb-cat" class="select-field">
                <option value="Technology">Technology & SaaS</option><option value="Fashion">Fashion & Apparel</option><option value="Beauty & Skincare">Beauty & Skincare</option><option value="Food & Beverage">Food & Beverage</option><option value="Fitness">Fitness & Health</option><option value="Other">Other</option>
              </select>
            </div>
            <div id="rb-err" style="color: var(--danger); font-size: 13px; margin-bottom: 12px;"></div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">Create Brand Workspace</button>
            <button type="button" class="btn btn-outline btn-sm" style="margin-top: 10px; width: 100%;" onclick="App.closeModal()">Back</button>
          </form>
        `);
      },

      async handleRegisterBrand(e) {
        e.preventDefault();
        try {
          await API.post('/api/auth/register-brand', {
            business_name: document.getElementById('rb-biz').value,
            contact_person: document.getElementById('rb-contact').value,
            email: document.getElementById('rb-email').value,
            password: document.getElementById('rb-pass').value,
            category: document.getElementById('rb-cat').value
          });
          State.user = await API.get('/api/auth/me');
          App.renderNav();
          App.closeModal();
          Router.navigate('/dashboard');
        } catch (err) {
          document.getElementById('rb-err').innerText = err.message;
        }
      }
    };

    const Router = {
      navigate(route) { window.location.hash = route; },
      async route() {
        const hash = window.location.hash.slice(1) || '/';
        const main = document.getElementById('main-content');
        if (hash === '/') main.innerHTML = Views.landing();
        else if (hash.startsWith('/discover')) main.innerHTML = await Views.discover();
        else if (hash.startsWith('/creator/')) main.innerHTML = await Views.creatorProfile(hash.split('/')[2]);
        else if (hash === '/opportunities') main.innerHTML = await Views.opportunities();
        else if (hash === '/dashboard') {
          if (!State.user) { App.openLoginModal(); Router.navigate('/'); return; }
          main.innerHTML = await Views.dashboard();
        } else {
          main.innerHTML = Views.landing();
        }
      }
    };

    window.addEventListener('hashchange', () => Router.route());

    // =========================================================================
    // VIEWS: EDITORIAL PRODUCT EXPERIENCE & WORKSPACES
    // =========================================================================
    const Views = {
      landing() {
        return `
          <!-- 1. HERO SECTION -->
          <section class="hero-section">
            <div class="container">
              <div class="hero-pill">
                <span style="display:inline-block; width:6px; height:6px; background:#06B6D4; border-radius:50%;"></span>
                Enterprise Creator Marketing & Collaboration Infrastructure
              </div>
              <h1 class="hero-title">Discover the right creators.<br><span>Build high-performing partnerships.</span></h1>
              <p class="hero-desc">Creator Hive replaces disconnected spreadsheets, blind outreach, and opaque deliverables with a single workspace for creator search, verified analytics, and campaign automation.</p>
              <div class="hero-cta-group">
                <button class="btn btn-primary" onclick="App.openGetStartedModal()">Get Started Free &rarr;</button>
                <button class="btn btn-outline" onclick="Router.navigate('/discover')">Explore Creator Directory</button>
              </div>

              <!-- Product Preview Frame -->
              <div class="preview-container">
                <div class="preview-bar">
                  <div class="preview-dot"></div><div class="preview-dot"></div><div class="preview-dot"></div>
                  <span style="font-size: 11px; color: var(--text-dim); margin-left: 10px;">Creator Hive OS — Discovery Console & Campaign Pipeline</span>
                </div>
                <div class="preview-body">
                  <div style="border-right: 1px solid var(--border-subtle); padding-right: 18px;">
                    <div style="font-size: 12px; font-weight: 700; color: var(--text-dim); margin-bottom: 12px;">ACTIVE ROSTER</div>
                    <div style="background: var(--bg-elevated); padding: 10px; border-radius: 6px; margin-bottom: 8px;">
                      <strong style="font-size: 13px;">Priya Sharma</strong>
                      <div style="font-size: 11px; color: var(--text-muted);">Fashion & Tech • 82K</div>
                    </div>
                    <div style="background: rgba(37,99,235,0.15); border: 1px solid rgba(37,99,235,0.3); padding: 10px; border-radius: 6px;">
                      <strong style="font-size: 13px; color: #93C5FD;">Aman Verma</strong>
                      <div style="font-size: 11px; color: var(--text-muted);">95% Hive Match • 110K</div>
                    </div>
                  </div>
                  <div>
                    <div class="flex justify-between items-center" style="margin-bottom: 14px;">
                      <div>
                        <strong style="font-size: 15px;">Creator Match Intelligence</strong>
                        <div style="font-size: 12px; color: var(--text-muted);">Rule-based compatibility against Summer Launch Brief</div>
                      </div>
                      <span class="badge badge-verified">94% Compatibility</span>
                    </div>
                    <div class="grid grid-cols-3 gap-3" style="font-size: 12px;">
                      <div style="background: var(--bg-elevated); padding: 12px; border-radius: 6px;">
                        <span style="color: var(--text-muted);">Response Rate</span>
                        <div style="font-size: 16px; font-weight: 700; color: var(--success); margin-top: 4px;">98%</div>
                      </div>
                      <div style="background: var(--bg-elevated); padding: 12px; border-radius: 6px;">
                        <span style="color: var(--text-muted);">On-Time Delivery</span>
                        <div style="font-size: 16px; font-weight: 700; color: var(--success); margin-top: 4px;">100%</div>
                      </div>
                      <div style="background: var(--bg-elevated); padding: 12px; border-radius: 6px;">
                        <span style="color: var(--text-muted);">Target Channel</span>
                        <div style="font-size: 16px; font-weight: 700; color: #93C5FD; margin-top: 4px;">Instagram Reels</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- 2. BRAND & CREATOR VALUE PILLARS -->
          <section class="section-wrap" style="background: var(--bg-surface);">
            <div class="container">
              <div class="section-header">
                <div class="section-label">Enterprise Architecture</div>
                <h2 class="section-heading">Designed for precision collaboration.</h2>
                <p class="section-subtext">Both sides of the creator economy get a dedicated workspace tailored to performance.</p>
              </div>
              <div class="grid grid-cols-2 gap-8">
                <div class="card card-hover" style="padding: 36px;">
                  <div class="badge badge-cyan" style="margin-bottom: 16px;">FOR BRANDS & AGENCIES</div>
                  <h3 style="font-size: 24px; font-weight: 800; margin-bottom: 12px;">Scalable Creator Operations</h3>
                  <p style="color: var(--text-muted); font-size: 15px; margin-bottom: 24px;">Discover authentic creators, launch targeted campaign briefs, receive structured proposals, and keep a lifetime Relationship Memory across repeated partnerships.</p>
                  <ul style="list-style: none; display: flex; flex-direction: column; gap: 10px; font-size: 14px; color: var(--text-muted);">
                    <li>✔ Granular creator discovery with engagement analytics</li>
                    <li>✔ Deterministic match compatibility explanations</li>
                    <li>✔ Built-in proposals, approval staging & messaging</li>
                  </ul>
                </div>
                <div class="card card-hover" style="padding: 36px;">
                  <div class="badge badge-primary" style="margin-bottom: 16px;">FOR CONTENT CREATORS</div>
                  <h3 style="font-size: 24px; font-weight: 800; margin-bottom: 12px;">Your Verified Media Kit</h3>
                  <p style="color: var(--text-muted); font-size: 15px; margin-bottom: 24px;">Eliminate manual PDF media kits. Showcase real verified audience numbers across Instagram, YouTube, and multi-platforms, set rates, and apply directly to sponsored briefs.</p>
                  <ul style="list-style: none; display: flex; flex-direction: column; gap: 10px; font-size: 14px; color: var(--text-muted);">
                    <li>✔ Zero-friction registration without forced initial setup</li>
                    <li>✔ Live channel management & follower tracking</li>
                    <li>✔ Direct sponsored briefs with clear budgets & guidelines</li>
                  </ul>
                </div>
              </div>
            </div>
          </section>

          <!-- 3. UNIQUE FEATURE: HIVE MATCH INTELLIGENCE -->
          <section class="section-wrap" id="intelligence-section">
            <div class="container">
              <div class="section-header">
                <div class="section-label">Proprietary Technology</div>
                <h2 class="section-heading">Hive Match Intelligence™</h2>
                <p class="section-subtext">No black-box hallucinations. We use explainable rule-based parameters combining reliability scores, platform compatibility, audience tiers, and category focus.</p>
              </div>
              <div class="card" style="max-width: 850px; margin: 0 auto; padding: 36px; border-color: rgba(37, 99, 235, 0.35);">
                <div class="flex justify-between items-center" style="margin-bottom: 24px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 16px;">
                  <div>
                    <h3 style="font-size: 20px; font-weight: 800;">Explainable Match Engine</h3>
                    <div style="font-size: 13px; color: var(--text-muted);">Live Multi-Parameter Compatibility Matrix</div>
                  </div>
                  <span class="badge badge-cyan" style="font-size: 13px;">Deterministic Scoring</span>
                </div>
                <div class="grid grid-cols-2 gap-6" style="margin-bottom: 24px;">
                  <div>
                    <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 4px;">Niche & Category Affinity</div>
                    <div style="font-weight: 700;">Direct Match (35 Points)</div>
                  </div>
                  <div>
                    <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 4px;">Target Platform Alignment</div>
                    <div style="font-weight: 700;">Active Channel Verified (30 Points)</div>
                  </div>
                  <div>
                    <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 4px;">Audience Tier Relevance</div>
                    <div style="font-weight: 700;">Optimal Bracket (20 Points)</div>
                  </div>
                  <div>
                    <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 4px;">Geographic Compatibility</div>
                    <div style="font-weight: 700;">Market Match (15 Points)</div>
                  </div>
                </div>
                <p style="font-size: 13px; color: var(--text-dim); line-height: 1.6;">Every recommendation clearly outlines why a creator matches a campaign rather than presenting an arbitrary number. Brands see verified response rate, approval punctuality, and category alignment up front.</p>
              </div>
            </div>
          </section>

          <!-- 4. LEADERSHIP & TEAM -->
          <section class="section-wrap" id="leadership-section" style="background: var(--bg-surface);">
            <div class="container" style="max-width: 900px;">
              <div class="section-header">
                <div class="section-label">Leadership</div>
                <h2 class="section-heading">Executive Team</h2>
                <p class="section-subtext">Building high-trust infrastructure for the creator economy.</p>
              </div>
              <div class="grid grid-cols-2 gap-8">
                <div class="card" style="padding: 32px;">
                  <div style="width: 56px; height: 56px; border-radius: 50%; background: var(--bg-elevated); border: 2px solid var(--accent-primary); display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: 800; color: #93C5FD; margin-bottom: 16px;">SC</div>
                  <h3 style="font-size: 20px; font-weight: 800;">Sunil Chopra</h3>
                  <div style="font-size: 13px; color: var(--accent-cyan); font-weight: 600; margin-bottom: 12px;">Founder</div>
                  <p style="font-size: 14px; color: var(--text-muted); line-height: 1.6;">Directs corporate strategy, enterprise governance, and business expansion, driving the vision to scale Creator Hive across India and global markets.</p>
                </div>
                <div class="card" style="padding: 32px;">
                  <div style="width: 56px; height: 56px; border-radius: 50%; background: var(--bg-elevated); border: 2px solid var(--accent-cyan); display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: 800; color: #67E8F9; margin-bottom: 16px;">SC</div>
                  <h3 style="font-size: 20px; font-weight: 800;">Sidharth Chopra</h3>
                  <div style="font-size: 13px; color: var(--accent-cyan); font-weight: 600; margin-bottom: 12px;">Chief Executive Officer</div>
                  <p style="font-size: 14px; color: var(--text-muted); line-height: 1.6;">14-year-old technology architect directing platform product strategy, technical implementation, and end-to-end workflow experiences for brands and creators.</p>
                </div>
              </div>
            </div>
          </section>

          <!-- 5. FAQ -->
          <section class="section-wrap">
            <div class="container" style="max-width: 800px;">
              <div class="section-header">
                <div class="section-label">Questions & Answers</div>
                <h2 class="section-heading">Frequently Asked Questions</h2>
              </div>
              <div class="faq-item">
                <div class="faq-trigger" onclick="this.parentElement.classList.toggle('active')">
                  Why does creator sign-up only require basic credentials? <span class="faq-icon">+</span>
                </div>
                <div class="faq-answer">
                  Creator Hive prioritizes frictionless onboarding. Creators can get started immediately without having to link social accounts or fill out categories in registration forms. Channel linking and media-kit customisation take place comfortably inside the dedicated creator workspace.
                </div>
              </div>
              <div class="faq-item">
                <div class="faq-trigger" onclick="this.parentElement.classList.toggle('active')">
                  How does Hive Match Intelligence calculate fit? <span class="faq-icon">+</span>
                </div>
                <div class="faq-answer">
                  Rather than using opaque machine learning placeholders, our matching system is fully explainable. It analyzes niche compatibility, target platforms, follower tier bounds, geographic focus, and actual creator reliability rates.
                </div>
              </div>
              <div class="faq-item">
                <div class="faq-trigger" onclick="this.parentElement.classList.toggle('active')">
                  What is Creator Hive Relationship Memory™? <span class="faq-icon">+</span>
                </div>
                <div class="faq-answer">
                  When brands collaborate with a creator repeatedly, Creator Hive preserves previous contract details, deliverables history, communication notes, and approval records so you never start from zero.
                </div>
              </div>
            </div>
          </section>

          <!-- 6. FINAL CTA & FOOTER -->
          <section class="section-wrap" style="text-align: center; background: radial-gradient(circle at 50% 100%, rgba(37, 99, 235, 0.15) 0%, transparent 60%);">
            <div class="container">
              <h2 class="section-heading" style="font-size: 42px; margin-bottom: 16px;">Ready to elevate your creator partnerships?</h2>
              <p class="section-subtext" style="margin-bottom: 40px;">Join leading brands and creators managing end-to-end campaigns on Creator Hive.</p>
              <div class="flex justify-center gap-4">
                <button class="btn btn-primary" onclick="App.openGetStartedModal()">Get Started Now &rarr;</button>
                <button class="btn btn-outline" onclick="Router.navigate('/discover')">Discover Talent</button>
              </div>
            </div>
          </section>

          <footer style="padding: 40px 0; border-top: 1px solid var(--border-subtle); font-size: 13px; color: var(--text-dim);">
            <div class="container flex justify-between items-center">
              <div>© 2026 Creator Hive Enterprise. All rights reserved.</div>
              <div class="flex gap-6">
                <span>Founder: Sunil Chopra</span>
                <span>CEO: Sidharth Chopra</span>
              </div>
            </div>
          </footer>
        `;
      },

      // DASHBOARD VIEW
      async dashboard() {
        const u = State.user;
        let content = '';
        if (u.role === 'Brand') content = await Views.brandDashboard();
        else if (u.role === 'Creator') content = await Views.creatorDashboard();

        return `
          <div class="dashboard-layout">
            <aside class="sidebar">
              <div>
                <div style="font-size: 11px; font-weight: 700; color: var(--text-dim); letter-spacing: 1px; margin-bottom: 14px; text-transform: uppercase;">
                  ${u.role} Workspace
                </div>
                <ul class="sidebar-menu">
                  <li class="sidebar-link active" id="sb-overview" onclick="Views.switchTab('overview')">Overview</li>
                  ${u.role === 'Creator' ? `
                    <li class="sidebar-link" id="sb-profile" onclick="Views.switchTab('profile')">My Media Kit & Channels</li>
                    <li class="sidebar-link" id="sb-apps" onclick="Views.switchTab('creator-apps')">Campaign Applications</li>
                  ` : ''}
                  ${u.role === 'Brand' ? `
                    <li class="sidebar-link" id="sb-campaigns" onclick="Views.switchTab('campaigns')">Campaign Management</li>
                    <li class="sidebar-link" id="sb-shortlists" onclick="Views.switchTab('shortlists')">Saved Shortlists</li>
                  ` : ''}
                  <li class="sidebar-link" id="sb-inbox" onclick="Views.switchTab('inbox')">Direct Messaging</li>
                  <li class="sidebar-link" id="sb-notifications" onclick="Views.switchTab('notifications')">Notifications</li>
                </ul>
              </div>
              <div style="border-top: 1px solid var(--border-subtle); padding-top: 16px;">
                <div style="font-size: 13px; font-weight: 600; color: var(--text-main);">${u.email}</div>
                <div style="font-size: 11px; color: var(--text-dim); margin-bottom: 12px;">Active Role: ${u.role}</div>
                <button class="btn btn-outline btn-sm" style="width: 100%;" onclick="App.logout()">Log Out</button>
              </div>
            </aside>
            <section class="main-viewport" id="dash-vp">${content}</section>
          </div>
        `;
      },

      async switchTab(tab) {
        document.querySelectorAll('.sidebar-link').forEach(el => el.classList.remove('active'));
        const link = document.getElementById(`sb-${tab}`) || document.getElementById('sb-overview');
        if (link) link.classList.add('active');

        const vp = document.getElementById('dash-vp');
        if (tab === 'overview') vp.innerHTML = State.user.role === 'Brand' ? await Views.brandDashboard() : await Views.creatorDashboard();
        else if (tab === 'profile') vp.innerHTML = await Views.creatorProfileWorkspace();
        else if (tab === 'creator-apps') vp.innerHTML = await Views.creatorApplicationsView();
        else if (tab === 'inbox') vp.innerHTML = await Views.inboxView();
        else if (tab === 'campaigns') vp.innerHTML = await Views.brandCampaignsView();
        else if (tab === 'shortlists') vp.innerHTML = await Views.brandShortlistsView();
        else if (tab === 'notifications') vp.innerHTML = await Views.notificationsView();
      },

      // CREATOR DASHBOARD
      async creatorDashboard() {
        const data = await API.get('/api/dashboard/creator');
        return `
          <div class="flex justify-between items-center" style="margin-bottom: 30px;">
            <div>
              <h1 style="font-size: 26px; font-weight: 800;">Creator Hub — ${State.user.profile.display_name}</h1>
              <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">
                Media Kit Completion: <strong style="color: #93C5FD;">${data.metrics.profile_completion}%</strong>
              </div>
            </div>
            <div class="flex gap-2">
              <button class="btn btn-outline btn-sm" onclick="Views.switchTab('profile')">Edit Media Kit</button>
              <button class="btn btn-primary btn-sm" onclick="Router.navigate('/opportunities')">Browse Campaigns</button>
            </div>
          </div>

          <div class="grid grid-cols-4 gap-4" style="margin-bottom: 32px;">
            <div class="card">
              <div style="font-size: 12px; color: var(--text-muted);">Total Audience</div>
              <div style="font-size: 24px; font-weight: 800; margin-top: 4px;">${data.metrics.total_audience.toLocaleString()}</div>
            </div>
            <div class="card">
              <div style="font-size: 12px; color: var(--text-muted);">Profile Impressions</div>
              <div style="font-size: 24px; font-weight: 800; margin-top: 4px;">${data.metrics.profile_views}</div>
            </div>
            <div class="card">
              <div style="font-size: 12px; color: var(--text-muted);">Pitches Submitted</div>
              <div style="font-size: 24px; font-weight: 800; margin-top: 4px;">${data.metrics.applications_submitted}</div>
            </div>
            <div class="card">
              <div style="font-size: 12px; color: var(--text-muted);">Active Collaborations</div>
              <div style="font-size: 24px; font-weight: 800; margin-top: 4px; color: var(--success);">${data.metrics.active_collaborations}</div>
            </div>
          </div>

          <div class="card" style="margin-bottom: 24px;">
            <div class="flex justify-between items-center" style="margin-bottom: 16px;">
              <h3 style="font-size: 16px; font-weight: 700;">Connected Social Channels</h3>
              <button class="btn btn-outline btn-sm" onclick="Views.openAddChannelModal()">+ Connect Channel</button>
            </div>
            ${data.channels.length === 0 ? `
              <div style="text-align: center; padding: 32px; background: var(--bg-surface); border-radius: 8px;">
                <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 12px;">No channels linked to your profile yet.</p>
                <button class="btn btn-primary btn-sm" onclick="Views.openAddChannelModal()">Link Instagram / YouTube</button>
              </div>
            ` : `
              <div class="grid grid-cols-3 gap-4">
                ${data.channels.map(sc => `
                  <div style="background: var(--bg-surface); padding: 16px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                    <div class="flex justify-between items-center">
                      <span class="badge badge-primary">${sc.platform}</span>
                      <span style="font-size: 12px; font-weight: 700; color: #93C5FD;">${sc.followers.toLocaleString()}</span>
                    </div>
                    <div style="font-size: 14px; font-weight: 700; margin-top: 10px;">${sc.channel_name}</div>
                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Avg. Engagement: ${sc.engagement}%</div>
                  </div>
                `).join('')}
              </div>
            `}
          </div>
        `;
      },

      // CREATOR PROFILE WORKSPACE
      async creatorProfileWorkspace() {
        const p = await API.get(`/api/creators/${State.user.profile.id}`);
        return `
          <div style="max-width: 850px;">
            <h1 style="font-size: 26px; font-weight: 800; margin-bottom: 6px;">Creator Media Kit Configuration</h1>
            <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 28px;">Keep your verified footprint, deliverables rates, and editorial bio updated for discovering brands.</p>

            <div class="card" style="margin-bottom: 28px;">
              <h3 style="font-size: 17px; font-weight: 700; margin-bottom: 18px;">Editorial Profile</h3>
              <form onsubmit="Views.handleCreatorProfileUpdate(event)">
                <div class="grid grid-cols-2 gap-4">
                  <div class="form-group">
                    <label>Professional Display Name *</label>
                    <input type="text" id="ep-dn" class="input-field" value="${p.name}" required />
                  </div>
                  <div class="form-group">
                    <label>Primary Category *</label>
                    <input type="text" id="ep-cat" class="input-field" value="${p.category !== 'General Talent' ? p.category : ''}" placeholder="e.g. Technology, Fashion, Lifestyle" required />
                  </div>
                </div>
                <div class="grid grid-cols-2 gap-4">
                  <div class="form-group">
                    <label>Specific Focus / Niche</label>
                    <input type="text" id="ep-niche" class="input-field" value="${p.niche !== 'Content Creation' ? p.niche : ''}" placeholder="e.g. Smartphone Unboxings, Ethnic Wear" />
                  </div>
                  <div class="form-group">
                    <label>Languages</label>
                    <input type="text" id="ep-lang" class="input-field" value="${p.languages}" />
                  </div>
                </div>
                <div class="form-group">
                  <label>Media Kit Biography</label>
                  <textarea id="ep-bio" class="textarea-field" rows="4">${p.bio}</textarea>
                </div>
                <div class="grid grid-cols-2 gap-4">
                  <div class="form-group"><label>Base Rate: Reel (₹)</label><input type="number" id="ep-rr" class="input-field" value="${p.rates.reel}" /></div>
                  <div class="form-group"><label>Base Rate: Dedicated Video (₹)</label><input type="number" id="ep-rv" class="input-field" value="${p.rates.video}" /></div>
                </div>
                <button type="submit" class="btn btn-primary btn-sm">Save Profile Updates</button>
              </form>
            </div>

            <div class="card">
              <div class="flex justify-between items-center" style="margin-bottom: 18px;">
                <div>
                  <h3 style="font-size: 17px; font-weight: 700;">Connected Social Accounts</h3>
                  <div style="font-size: 12px; color: var(--text-muted);">Manage Instagram, YouTube & verified channels.</div>
                </div>
                <button class="btn btn-outline btn-sm" onclick="Views.openAddChannelModal()">+ Connect Platform</button>
              </div>
              <div id="channels-container">
                ${p.social_channels.length === 0 ? '<p style="color: var(--text-muted); font-size: 13px;">No platforms connected yet.</p>' : p.social_channels.map(sc => `
                  <div style="background: var(--bg-surface); padding: 14px 18px; border-radius: 8px; border: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div>
                      <strong>${sc.platform}</strong>: <a href="${sc.profile_url}" target="_blank" style="color:#93C5FD;">${sc.channel_name}</a>
                      <span style="font-size: 12px; color: var(--text-muted); margin-left: 12px;">${sc.followers.toLocaleString()} followers • ${sc.engagement_rate}% engagement</span>
                    </div>
                    <button class="btn btn-outline btn-sm btn-danger" onclick="Views.deleteChannel(${sc.id})">Remove</button>
                  </div>
                `).join('')}
              </div>
            </div>
          </div>
        `;
      },

      async handleCreatorProfileUpdate(e) {
        e.preventDefault();
        await API.post('/api/creator/profile/update', {
          display_name: document.getElementById('ep-dn').value,
          category: document.getElementById('ep-cat').value,
          niche: document.getElementById('ep-niche').value,
          languages: document.getElementById('ep-lang').value,
          bio: document.getElementById('ep-bio').value,
          base_rate_reel: parseFloat(document.getElementById('ep-rr').value || '0'),
          base_rate_video: parseFloat(document.getElementById('ep-rv').value || '0')
        });
        alert('Media Kit updated successfully.');
        Views.switchTab('profile');
      },

      openAddChannelModal() {
        App.openModal(`
          <h2 style="font-size: 20px; font-weight: 800; margin-bottom: 6px;">Connect Social Platform</h2>
          <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 20px;">Link Instagram, YouTube or social handles.</p>
          <form onsubmit="Views.handleAddChannel(event)">
            <div class="form-group"><label>Platform *</label>
              <select id="ac-plat" class="select-field">
                <option value="Instagram">Instagram</option><option value="YouTube">YouTube</option><option value="TikTok">TikTok</option><option value="Facebook">Facebook</option><option value="LinkedIn">LinkedIn</option><option value="X">X</option>
              </select>
            </div>
            <div class="form-group"><label>Handle / Channel Name *</label><input type="text" id="ac-name" class="input-field" required placeholder="@creatorhandle" /></div>
            <div class="form-group"><label>Profile URL *</label><input type="text" id="ac-url" class="input-field" required placeholder="https://instagram.com/creatorhandle" /></div>
            <div class="grid grid-cols-2 gap-3">
              <div class="form-group"><label>Audience / Followers *</label><input type="number" id="ac-foll" class="input-field" required placeholder="25000" /></div>
              <div class="form-group"><label>Engagement Rate (%)</label><input type="number" step="0.1" id="ac-eng" class="input-field" value="3.5" /></div>
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">Save Channel</button>
            <button type="button" class="btn btn-outline btn-sm" style="margin-top: 10px; width: 100%;" onclick="App.closeModal()">Cancel</button>
          </form>
        `);
      },

      async handleAddChannel(e) {
        e.preventDefault();
        await API.post('/api/creator/channels/add', {
          platform: document.getElementById('ac-plat').value,
          channel_name: document.getElementById('ac-name').value,
          profile_url: document.getElementById('ac-url').value,
          followers_count: parseInt(document.getElementById('ac-foll').value || '0'),
          engagement_rate: parseFloat(document.getElementById('ac-eng').value || '0')
        });
        App.closeModal();
        Views.switchTab('profile');
      },

      async deleteChannel(id) {
        if (!confirm('Are you sure you want to remove this channel?')) return;
        await API.delete(`/api/creator/channels/${id}`);
        Views.switchTab('profile');
      },

      // CREATOR APPLICATIONS VIEW
      async creatorApplicationsView() {
        const res = await API.get('/api/dashboard/creator');
        return `
          <div style="max-width: 900px;">
            <div class="flex justify-between items-center" style="margin-bottom: 24px;">
              <div>
                <h1 style="font-size: 26px; font-weight: 800;">Campaign Proposals</h1>
                <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">Track pitches and submit deliverables.</div>
              </div>
              <button class="btn btn-primary btn-sm" onclick="Router.navigate('/opportunities')">Browse More Briefs</button>
            </div>
            ${res.applications.length === 0 ? '<div class="card" style="text-align:center; padding: 40px; color: var(--text-muted);">You have not pitched to any campaigns yet.</div>' : `
              <div style="display: flex; flex-direction: column; gap: 14px;">
                ${res.applications.map(a => `
                  <div class="card">
                    <div class="flex justify-between items-center">
                      <div>
                        <h3 style="font-size: 16px; font-weight: 700;">${a.campaign_title}</h3>
                        <div style="font-size: 13px; color: var(--text-muted); margin-top: 2px;">Brand: ${a.brand_name} • Pitch Quote: ₹${a.quote.toLocaleString()} • ${a.created_at}</div>
                      </div>
                      <span class="badge ${a.status === 'Accepted' ? 'badge-verified' : 'badge-primary'}">${a.status}</span>
                    </div>
                    ${a.status === 'Accepted' ? `
                      <div style="margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 13px; color: #93C5FD;">Collaboration active. Submit your preview URL for review.</span>
                        <button class="btn btn-primary btn-sm" onclick="Views.openSubmitDeliverableModal(${a.id})">Submit Content</button>
                      </div>
                    ` : ''}
                  </div>
                `).join('')}
              </div>
            `}
          </div>
        `;
      },

      openSubmitDeliverableModal(appId) {
        App.openModal(`
          <h2 style="font-size: 20px; font-weight: 800; margin-bottom: 6px;">Submit Collaboration Content</h2>
          <form onsubmit="Views.handleSubmitDeliverable(event, ${appId})">
            <div class="form-group"><label>Published URL / Preview Link *</label><input type="text" id="sd-url" class="input-field" required placeholder="https://instagram.com/reel/..." /></div>
            <div class="form-group"><label>Notes / Captions</label><textarea id="sd-notes" class="textarea-field" rows="3"></textarea></div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">Submit for Review</button>
            <button type="button" class="btn btn-outline btn-sm" style="margin-top: 10px; width: 100%;" onclick="App.closeModal()">Cancel</button>
          </form>
        `);
      },

      async handleSubmitDeliverable(e, appId) {
        e.preventDefault();
        await API.post('/api/campaigns/content/submit', {
          application_id: appId,
          content_url: document.getElementById('sd-url').value,
          notes: document.getElementById('sd-notes').value
        });
        alert('Deliverable submitted successfully.');
        App.closeModal();
        Views.switchTab('creator-apps');
      },

      // BRAND DASHBOARD
      async brandDashboard() {
        const data = await API.get('/api/dashboard/brand');
        return `
          <div class="flex justify-between items-center" style="margin-bottom: 30px;">
            <div>
              <h1 style="font-size: 26px; font-weight: 800;">Enterprise Overview — ${State.user.profile.business_name}</h1>
              <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">Recruitment pipeline & active creator campaigns</div>
            </div>
            <button class="btn btn-primary btn-sm" onclick="Views.openNewCampaignModal()">+ Create Campaign Brief</button>
          </div>

          <div class="grid grid-cols-4 gap-4" style="margin-bottom: 32px;">
            <div class="card">
              <div style="font-size: 12px; color: var(--text-muted);">Active Briefs</div>
              <div style="font-size: 24px; font-weight: 800; margin-top: 4px;">${data.metrics.active_campaigns}</div>
            </div>
            <div class="card">
              <div style="font-size: 12px; color: var(--text-muted);">Proposals Received</div>
              <div style="font-size: 24px; font-weight: 800; margin-top: 4px;">${data.metrics.total_applications}</div>
            </div>
            <div class="card">
              <div style="font-size: 12px; color: var(--text-muted);">Shortlisted Creators</div>
              <div style="font-size: 24px; font-weight: 800; margin-top: 4px;">${data.metrics.shortlisted_creators}</div>
            </div>
            <div class="card">
              <div style="font-size: 12px; color: var(--text-muted);">Conversations</div>
              <div style="font-size: 24px; font-weight: 800; margin-top: 4px;">${data.metrics.conversations}</div>
            </div>
          </div>

          <div class="card">
            <h3 style="font-size: 17px; font-weight: 700; margin-bottom: 16px;">Active Briefs & Proposals</h3>
            ${data.campaigns.length === 0 ? '<p style="color: var(--text-muted); font-size: 13px;">No campaigns active. Click "+ Create Campaign Brief" to launch your first brief.</p>' : `
              <div style="display: flex; flex-direction: column; gap: 14px;">
                ${data.campaigns.map(c => `
                  <div style="background: var(--bg-surface); padding: 18px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                    <div class="flex justify-between items-center">
                      <div>
                        <strong>${c.title}</strong>
                        <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Budget: ₹${c.budget.toLocaleString()} • ${c.applications_count} Proposals</div>
                      </div>
                      <button class="btn btn-outline btn-sm" onclick="Views.switchTab('campaigns')">Review Applications</button>
                    </div>
                  </div>
                `).join('')}
              </div>
            `}
          </div>
        `;
      },

      openNewCampaignModal() {
        App.openModal(`
          <h2 style="font-size: 22px; font-weight: 800; margin-bottom: 6px;">Create Campaign Brief</h2>
          <form onsubmit="Views.handleCreateCampaign(event)">
            <div class="form-group"><label>Campaign Title *</label><input type="text" id="nc-title" class="input-field" required placeholder="Diwali Product Launch & Awareness" /></div>
            <div class="grid grid-cols-2 gap-3">
              <div class="form-group"><label>Category *</label><input type="text" id="nc-cat" class="input-field" value="Fashion" required /></div>
              <div class="form-group"><label>Objective *</label><input type="text" id="nc-obj" class="input-field" required placeholder="Conversions & Brand Awareness" /></div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="form-group"><label>Budget (₹ INR) *</label><input type="number" id="nc-bud" class="input-field" required placeholder="75000" /></div>
              <div class="form-group"><label>Audience Tier</label>
                <select id="nc-tier" class="select-field">
                  <option value="10K–50K">10K–50K</option><option value="50K–100K">50K–100K</option><option value="100K–500K">100K–500K</option><option value="1M+">1M+</option>
                </select>
              </div>
            </div>
            <div class="form-group"><label>Required Deliverables *</label><input type="text" id="nc-del" class="input-field" required placeholder="1x Dedicated Reel, 2x Instagram Stories" /></div>
            <div class="form-group"><label>Campaign Description & Guidelines *</label><textarea id="nc-desc" class="textarea-field" rows="3" required placeholder="Brief description of the product, key talking points, and collaboration requirements."></textarea></div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">Publish Campaign</button>
            <button type="button" class="btn btn-outline btn-sm" style="margin-top: 10px; width: 100%;" onclick="App.closeModal()">Cancel</button>
          </form>
        `);
      },

      async handleCreateCampaign(e) {
        e.preventDefault();
        await API.post('/api/campaigns/create', {
          title: document.getElementById('nc-title').value,
          category: document.getElementById('nc-cat').value,
          objective: document.getElementById('nc-obj').value,
          budget: parseFloat(document.getElementById('nc-bud').value),
          audience_range: document.getElementById('nc-tier').value,
          deliverables: document.getElementById('nc-del').value,
          description: document.getElementById('nc-desc').value,
          target_platforms: ['Instagram']
        });
        App.closeModal();
        Views.switchTab('campaigns');
      },

      async brandCampaignsView() {
        const data = await API.get('/api/dashboard/brand');
        return `
          <div>
            <div class="flex justify-between items-center" style="margin-bottom: 24px;">
              <h1 style="font-size: 26px; font-weight: 800;">Campaign Management</h1>
              <button class="btn btn-primary btn-sm" onclick="Views.openNewCampaignModal()">+ Create Brief</button>
            </div>
            ${data.campaigns.length === 0 ? '<div class="card" style="text-align:center; padding: 40px; color: var(--text-muted);">No campaigns published.</div>' : `
              <div style="display: flex; flex-direction: column; gap: 20px;">
                ${data.campaigns.map(c => `
                  <div class="card">
                    <div class="flex justify-between items-center" style="border-bottom: 1px solid var(--border-subtle); padding-bottom: 14px; margin-bottom: 16px;">
                      <div>
                        <h3 style="font-size: 18px; font-weight: 800;">${c.title}</h3>
                        <div style="font-size: 13px; color: var(--text-muted); margin-top: 2px;">Budget: ₹${c.budget.toLocaleString()} • Status: ${c.status}</div>
                      </div>
                      <span class="badge badge-primary">${c.applications.length} Proposals</span>
                    </div>
                    ${c.applications.length === 0 ? '<div style="font-size: 13px; color: var(--text-muted);">No creator proposals submitted for this brief yet.</div>' : `
                      <div style="display: flex; flex-direction: column; gap: 10px;">
                        ${c.applications.map(a => `
                          <div style="background: var(--bg-surface); padding: 14px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                              <strong>${a.creator_name}</strong> (Quote: ₹${a.proposed_price.toLocaleString()})
                              <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">"${a.proposal}"</div>
                            </div>
                            <div class="flex gap-2 items-center">
                              <span class="badge ${a.status === 'Accepted' ? 'badge-verified' : 'badge-primary'}">${a.status}</span>
                              ${a.status === 'Submitted' ? `
                                <button class="btn btn-primary btn-sm" onclick="Views.setAppStatus(${a.id}, 'Accepted')">Accept Bid</button>
                                <button class="btn btn-outline btn-sm btn-danger" onclick="Views.setAppStatus(${a.id}, 'Rejected')">Reject</button>
                              ` : ''}
                            </div>
                          </div>
                        `).join('')}
                      </div>
                    `}
                  </div>
                `).join('')}
              </div>
            `}
          </div>
        `;
      },

      async setAppStatus(appId, status) {
        await API.post('/api/campaigns/application/status', { app_id: appId, status_value: status });
        Views.switchTab('campaigns');
      },

      async brandShortlistsView() {
        const res = await API.get('/api/brand/shortlists');
        return `
          <div>
            <h1 style="font-size: 26px; font-weight: 800; margin-bottom: 24px;">Saved Talent Rosters</h1>
            ${res.shortlists.length === 0 ? '<div class="card" style="color:var(--text-muted);">No shortlists created yet.</div>' : `
              <div style="display: flex; flex-direction: column; gap: 20px;">
                ${res.shortlists.map(sl => `
                  <div class="card">
                    <h3 style="font-size: 18px; font-weight: 800; margin-bottom: 14px;">${sl.name} (${sl.count} Creators)</h3>
                    ${sl.creators.length === 0 ? '<div style="font-size: 13px; color: var(--text-muted);">No creators saved in this roster yet. Discover creators to add them here.</div>' : `
                      <div class="grid grid-cols-3 gap-4">
                        ${sl.creators.map(c => `
                          <div style="background: var(--bg-surface); padding: 14px; border-radius: 8px; border: 1px solid var(--border-subtle); display: flex; align-items: center; gap: 12px;">
                            <img src="${c.profile_image_url}" style="width: 44px; height: 44px; border-radius: 50%; object-fit: cover;" />
                            <div style="flex:1;">
                              <strong>${c.name}</strong>
                              <div style="font-size: 12px; color: var(--text-muted);">${c.category}</div>
                            </div>
                            <button class="btn btn-outline btn-sm" onclick="Router.navigate('/creator/${c.id}')">View</button>
                          </div>
                        `).join('')}
                      </div>
                    `}
                  </div>
                `).join('')}
              </div>
            `}
          </div>
        `;
      },

      // INBOX
      async inboxView() {
        const res = await API.get('/api/chat/conversations');
        const convos = res.conversations;
        if (convos.length > 0 && !State.activeConvoId) State.activeConvoId = convos[0].id;
        let messages = [];
        if (State.activeConvoId) {
          const mRes = await API.get(`/api/chat/${State.activeConvoId}/messages`);
          messages = mRes.messages;
        }

        return `
          <h1 style="font-size: 26px; font-weight: 800; margin-bottom: 24px;">Direct Messaging Console</h1>
          <div class="chat-container">
            <div class="chat-threads">
              ${convos.length === 0 ? '<div style="padding: 24px; color: var(--text-muted); font-size: 13px;">No conversations initialized. Connect with a creator from their profile.</div>' : convos.map(c => `
                <div class="thread-item ${c.id === State.activeConvoId ? 'active' : ''}" onclick="State.activeConvoId = ${c.id}; Views.switchTab('inbox');">
                  <div class="flex items-center gap-3">
                    <img src="${c.avatar || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100'}" style="width: 38px; height: 38px; border-radius: 50%; object-fit: cover;" />
                    <div style="flex:1; overflow:hidden;">
                      <div class="flex justify-between items-center">
                        <strong style="font-size: 14px;">${c.name}</strong>
                        <span style="font-size: 11px; color: var(--text-dim);">${c.last_message_time}</span>
                      </div>
                      <div style="font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px;">${c.last_message}</div>
                    </div>
                  </div>
                </div>
              `).join('')}
            </div>
            <div class="chat-stage">
              <div class="chat-messages" id="chat-msg-pane">
                ${messages.map(m => `
                  <div class="chat-bubble ${m.is_me ? 'mine' : 'theirs'}">
                    <div>${m.content}</div>
                    <div style="font-size: 10px; opacity: 0.7; text-align: right; margin-top: 4px;">${m.time}</div>
                  </div>
                `).join('')}
              </div>
              ${State.activeConvoId ? `
                <div style="padding: 16px; border-top: 1px solid var(--border-subtle); display: flex; gap: 10px;">
                  <input type="text" id="msg-input" class="input-field" placeholder="Write message..." onkeydown="if(event.key==='Enter') Views.sendDirectMessage();" />
                  <button class="btn btn-primary btn-sm" onclick="Views.sendDirectMessage()">Send</button>
                </div>
              ` : ''}
            </div>
          </div>
        `;
      },

      async sendDirectMessage() {
        const input = document.getElementById('msg-input');
        const content = input.value.trim();
        if (!content || !State.activeConvoId) return;
        await API.post('/api/chat/send', { conversation_id: State.activeConvoId, content });
        input.value = '';
        Views.switchTab('inbox');
      },

      async notificationsView() {
        const res = await API.get('/api/notifications');
        return `
          <div style="max-width: 800px;">
            <h1 style="font-size: 26px; font-weight: 800; margin-bottom: 24px;">Notifications</h1>
            ${res.notifications.length === 0 ? '<div class="card" style="color:var(--text-muted);">No new notifications.</div>' : `
              <div style="display: flex; flex-direction: column; gap: 10px;">
                ${res.notifications.map(n => `
                  <div class="card" style="padding: 16px;">
                    <div class="flex justify-between items-center">
                      <strong style="font-size: 14px;">${n.title}</strong>
                      <span style="font-size: 11px; color: var(--text-dim);">${n.created_at}</span>
                    </div>
                    <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">${n.content}</div>
                  </div>
                `).join('')}
              </div>
            `}
          </div>
        `;
      },

      // DISCOVERY DIRECTORY
      async discover() {
        const { q, category, audience, location } = State.discoveryFilters;
        const data = await API.get(`/api/creators/discover?q=${q}&category=${category}&audience=${audience}&location=${location}`);
        return `
          <div class="container" style="padding: 50px 0;">
            <div class="section-header" style="margin-bottom: 40px;">
              <div class="section-label">Verified Talent Directory</div>
              <h1 class="section-heading">Search Creators by Verified Footprint</h1>
              <p class="section-subtext">Filter creators using real reach, engagement parameters, and Collab Intelligence scores.</p>
            </div>

            <!-- Search & Filters -->
            <div class="card" style="margin-bottom: 32px; padding: 20px;">
              <div class="grid grid-cols-4 gap-3">
                <input type="text" class="input-field" placeholder="Search by name, handle, niche..." value="${q}" oninput="State.discoveryFilters.q = this.value; Views.refreshDiscovery();" />
                <select class="select-field" onchange="State.discoveryFilters.category = this.value; Views.refreshDiscovery();">
                  <option value="All">All Categories</option><option value="Technology">Technology</option><option value="Fashion">Fashion</option><option value="Fitness">Fitness</option><option value="Beauty">Beauty</option>
                </select>
                <select class="select-field" onchange="State.discoveryFilters.audience = this.value; Views.refreshDiscovery();">
                  <option value="All">All Audience Tiers</option><option value="1K–10K">1K–10K (Nano)</option><option value="10K–50K">10K–50K (Micro)</option><option value="50K–100K">50K–100K (Mid)</option><option value="100K–500K">100K–500K (Macro)</option>
                </select>
                <input type="text" class="input-field" placeholder="Filter by city (e.g. Jammu, Delhi)" value="${location}" oninput="State.discoveryFilters.location = this.value; Views.refreshDiscovery();" />
              </div>
            </div>

            <!-- Directory Grid -->
            <div class="grid grid-cols-3 gap-6">
              ${data.creators.map(c => `
                <div class="card card-hover" style="display: flex; flex-direction: column; justify-content: space-between;">
                  <div>
                    <div class="flex items-center gap-3" style="margin-bottom: 14px;">
                      <img src="${c.profile_image_url}" style="width: 54px; height: 54px; border-radius: 50%; object-fit: cover;" />
                      <div>
                        <div class="flex items-center gap-2">
                          <strong style="font-size: 16px;">${c.name}</strong>${c.is_verified ? '<span class="badge badge-verified" style="padding:2px 6px; font-size:9px;">VERIFIED</span>' : ''}
                        </div>
                        <div style="font-size: 12px; color: var(--text-muted);">${c.category} •${c.city}</div>
                      </div>
                    </div>
                    <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${c.bio}</p>
                    <div class="grid grid-cols-2 gap-2" style="background: var(--bg-surface); padding: 12px; border-radius: 8px; margin-bottom: 16px; font-size: 12px;">
                      <div>
                        <span style="color: var(--text-muted);">Audience:</span>
                        <div style="font-weight: 700; color: #93C5FD;">${c.total_followers.toLocaleString()}</div>
                      </div>
                      <div>
                        <span style="color: var(--text-muted);">Collab Score:</span>
                        <div style="font-weight: 700; color: var(--success);">${c.collab_score}/100</div>
                      </div>
                    </div>
                  </div>
                  <div class="flex gap-2">
                    <button class="btn btn-outline btn-sm" style="flex:1;" onclick="Router.navigate('/creator/${c.id}')">Media Kit</button>
                    ${State.user && State.user.role === 'Brand' ? `
                      <button class="btn btn-primary btn-sm" onclick="Views.handleChatInit(${c.id})">Message</button>
                    ` : ''}
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      },

      async refreshDiscovery() {
        document.getElementById('main-content').innerHTML = await Views.discover();
      },

      async handleChatInit(creatorId) {
        const res = await API.post('/api/chat/initiate', { creator_id: creatorId });
        State.activeConvoId = res.conversation_id;
        Router.navigate('/dashboard');
        setTimeout(() => Views.switchTab('inbox'), 100);
      },

      // CREATOR MEDIA KIT PROFILE
      async creatorProfile(id) {
        const c = await API.get(`/api/creators/${id}`);
        return `
          <div class="container" style="padding: 50px 0; max-width: 900px;">
            <div class="card" style="margin-bottom: 24px;">
              <div class="flex justify-between items-center" style="margin-bottom: 24px;">
                <div class="flex gap-4 items-center">
                  <img src="${c.profile_image_url}" style="width: 88px; height: 88px; border-radius: 50%; object-fit: cover; border: 2px solid var(--accent-primary);" />
                  <div>
                    <div class="flex items-center gap-2">
                      <h1 style="font-size: 24px; font-weight: 800;">${c.name}</h1>
                      ${c.is_verified ? '<span class="badge badge-verified">VERIFIED TALENT</span>' : ''}
                    </div>
                    <div style="font-size: 13px; color: var(--text-muted); margin-top: 2px;">
                      ${c.category} • ${c.niche} • ${c.city}, ${c.country}
                    </div>
                  </div>
                </div>
                ${State.user && State.user.role === 'Brand' ? `
                  <div class="flex gap-2">
                    <button class="btn btn-primary btn-sm" onclick="Views.handleChatInit(${c.id})">Direct Chat</button>
                    <button class="btn btn-outline btn-sm" onclick="Views.saveToShortlist(${c.id})">Save to Shortlist</button>
                  </div>
                ` : ''}
              </div>
              <p style="font-size: 14px; color: var(--text-muted); line-height: 1.6; margin-bottom: 24px;">${c.bio}</p>

              <!-- Channels Footprint -->
              <h3 style="font-size: 16px; font-weight: 700; margin-bottom: 14px;">Channel Reach</h3>
              <div class="grid grid-cols-3 gap-4" style="margin-bottom: 28px;">
                ${c.social_channels.map(sc => `
                  <div style="background: var(--bg-surface); padding: 16px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                    <div class="flex justify-between items-center">
                      <span class="badge badge-primary">${sc.platform}</span>
                      <strong style="color: #93C5FD;">${sc.followers.toLocaleString()}</strong>
                    </div>
                    <div style="font-size: 13px; margin-top: 8px; font-weight: 600;">${sc.channel_name}</div>
                    <div style="font-size: 11px; color: var(--text-dim); margin-top: 2px;">Engagement: ${sc.engagement_rate}%</div>
                  </div>
                `).join('')}
              </div>

              <!-- Reliability & Rates -->
              <div class="grid grid-cols-2 gap-6" style="border-top: 1px solid var(--border-subtle); padding-top: 20px;">
                <div>
                  <h4 style="font-size: 14px; font-weight: 700; margin-bottom: 10px;">Hive Collab Intelligence™</h4>
                  <div style="font-size: 13px; color: var(--text-muted);">
                    <div>Response Rate: <strong style="color: var(--success);">${c.collab_intelligence.response_rate}</strong></div>
                    <div style="margin-top: 4px;">On-Time Delivery: <strong style="color: var(--success);">${c.collab_intelligence.on_time_rate}</strong></div>
                    <div style="margin-top: 4px;">Completion Score: <strong style="color: #93C5FD;">${c.collab_intelligence.composite_score}/100</strong></div>
                  </div>
                </div>
                <div>
                  <h4 style="font-size: 14px; font-weight: 700; margin-bottom: 10px;">Deliverables Baseline Rates</h4>
                  <div style="font-size: 13px; color: var(--text-muted);">
                    <div>Instagram Reel: <strong>₹${c.rates.reel.toLocaleString()}</strong></div>
                    <div style="margin-top: 4px;">Dedicated Video: <strong>₹${c.rates.video.toLocaleString()}</strong></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        `;
      },

      async saveToShortlist(creatorId) {
        const res = await API.get('/api/brand/shortlists');
        if (res.shortlists.length === 0) return alert('No shortlist available.');
        const out = await API.post('/api/brand/shortlists/toggle', { shortlist_id: res.shortlists[0].id, creator_id: creatorId });
        alert(`Creator successfully ${out.action} Primary Shortlist.`);
      },

      // CAMPAIGN MARKETPLACE FOR CREATORS
      async opportunities() {
        const res = await API.get('/api/campaigns/opportunities');
        return `
          <div class="container" style="padding: 50px 0;">
            <div class="section-header">
              <div class="section-label">Opportunities Feed</div>
              <h1 class="section-heading">Open Sponsored Briefs</h1>
              <p class="section-subtext">Apply with your pitch and proposed quotation directly to brand briefs.</p>
            </div>
            <div style="display: flex; flex-direction: column; gap: 20px; max-width: 900px; margin: 0 auto;">
              ${res.campaigns.map(c => `
                <div class="card card-hover">
                  <div class="flex justify-between items-center" style="margin-bottom: 12px;">
                    <div>
                      <h3 style="font-size: 20px; font-weight: 800;">${c.title}</h3>
                      <div style="font-size: 13px; color: var(--text-muted); margin-top: 2px;">
                        By ${c.brand_name} • ${c.category} • Budget: <strong style="color:var(--success);">₹${c.budget.toLocaleString()}</strong>
                      </div>
                    </div>
                    <span class="badge badge-cyan">${c.match.score}% Hive Match</span>
                  </div>
                  <p style="font-size: 14px; color: var(--text-muted); margin-bottom: 16px; line-height: 1.6;">${c.description}</p>
                  <div style="background: var(--bg-surface); padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 13px;">
                    <strong>Deliverables:</strong> ${c.deliverables} • <strong>Location:</strong>${c.location}
                  </div>
                  <div class="flex justify-between items-center">
                    <div style="font-size: 12px; color: var(--text-dim);">
                      Match Factors: ${c.match.factors.join(', ')}
                    </div>
                    ${State.user && State.user.role === 'Creator' ? `
                      <button class="btn btn-primary btn-sm" onclick="Views.openApplyModal(${c.id}, '${c.title}')">Submit Proposal</button>
                    ` : '<button class="btn btn-outline btn-sm" onclick="App.openGetStartedModal()">Log in as Creator to Apply</button>'}
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      },

      openApplyModal(campId, title) {
        App.openModal(`
          <h2 style="font-size: 20px; font-weight: 800; margin-bottom: 4px;">Submit Proposal</h2>
          <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 20px;">Applying to: <strong>${title}</strong></div>
          <form onsubmit="Views.handleApplySubmit(event, ${campId})">
            <div class="form-group"><label>Proposed Quote (₹ INR) *</label><input type="number" id="ap-quote" class="input-field" required placeholder="25000" /></div>
            <div class="form-group"><label>Proposal & Creative Concept *</label><textarea id="ap-prop" class="textarea-field" rows="4" required placeholder="Explain your hook, target platform, and delivery timeline..."></textarea></div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">Send Pitch to Brand</button>
            <button type="button" class="btn btn-outline btn-sm" style="margin-top: 10px; width: 100%;" onclick="App.closeModal()">Cancel</button>
          </form>
        `);
      },

      async handleApplySubmit(e, campId) {
        e.preventDefault();
        try {
          await API.post('/api/campaigns/apply', {
            campaign_id: campId,
            proposed_price: parseFloat(document.getElementById('ap-quote').value),
            proposal: document.getElementById('ap-prop').value
          });
          alert('Proposal submitted successfully.');
          App.closeModal();
          Router.navigate('/dashboard');
        } catch (err) {
          alert(err.message);
        }
      }
    };

    window.addEventListener('DOMContentLoaded', () => App.init());
  </script>
</body>
</html>
"""

# ==============================================================================
# 9. SPA MOUNTING
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
async def serve_root():
    return HTMLResponse(content=MASTER_HTML, status_code=200)

@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found.")
    return HTMLResponse(content=MASTER_HTML, status_code=200)

# ==============================================================================
# 10. RUNNER
# ==============================================================================
if __name__ == "__main__":
    import uvicorn
    logger.info(f"Creator Hive Enterprise running on port {PORT}...")
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)