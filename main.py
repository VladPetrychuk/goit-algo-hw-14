from fastapi import FastAPI, Depends, HTTPException, status, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List
from database import SessionLocal, engine, Base, get_db
from models import Contact, User as ContactModel
from schemas import ContactCreate, ContactUpdate, Contact as ContactSchema, UserCreate
from datetime import date
from utils import hash_password, verify_password
from auth import create_access_token, verify_token
from fastapi.middleware.cors import CORSMiddleware
from fastapi_limiter.depends import RateLimiter
import cloudinary
import cloudinary.uploader
import os
from uuid import uuid4

Base.metadata.create_all(bind=engine)

app = FastAPI()

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

def send_verification_email(user_email: str, token: str):
    """
    Sends an email with a verification token.

    Parameters:
    - user_email (str): The user's email address.
    - token (str): Verification token to confirm email.
    """
    print(f"Email sent to {user_email} with token: {token}")

@app.post("/register/", response_model=ContactSchema)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """
    Registers a new user.

    Parameters:
    - user (UserCreate): User creation schema.
    - db (Session): Database session dependency.

    Returns:
    - ContactModel: Created user.
    """
    existing_user = db.query(ContactModel).filter(ContactModel.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="User with this email already exists")
    
    hashed_password = hash_password(user.password)
    new_user = ContactModel(email=user.email, hashed_password=hashed_password, verification_token=str(uuid4()))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    send_verification_email(new_user.email, new_user.verification_token)
    
    return new_user

@app.get("/verify-email/")
def verify_email(token: str, db: Session = Depends(get_db)):
    """
    Verifies user's email based on the provided token.

    Parameters:
    - token (str): The email verification token.
    - db (Session): Database session dependency.

    Returns:
    - dict: Success message if verification is successful.
    """
    user = db.query(ContactModel).filter(ContactModel.verification_token == token).first()
    if user:
        user.is_verified = True
        user.verification_token = None
        db.commit()
        return {"msg": "Email verified successfully"}
    raise HTTPException(status_code=400, detail="Invalid token")

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Authenticates a user and returns a JWT token.

    Parameters:
    - form_data (OAuth2PasswordRequestForm): Login form data with email and password.
    - db (Session): Database session dependency.

    Returns:
    - dict: Access token and token type.
    """
    user = db.query(ContactModel).filter(ContactModel.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_verified:
        raise HTTPException(status_code=401, detail="Email not verified")
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    Retrieves the current authenticated user based on the provided JWT token.

    Parameters:
    - token (str): OAuth2 token.
    - db (Session): Database session dependency.

    Returns:
    - ContactModel: The authenticated user.
    """
    payload = verify_token(token)
    user_email = payload.get("sub")
    if not user_email:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(ContactModel).filter(ContactModel.email == user_email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/contacts/", response_model=ContactSchema, dependencies=[Depends(RateLimiter(times=5, seconds=60))])
def create_contact(contact: ContactCreate, db: Session = Depends(get_db), current_user: ContactModel = Depends(get_current_user)):
    """
    Creates a new contact for the current authenticated user.

    Parameters:
    - contact (ContactCreate): The contact creation schema.
    - db (Session): Database session dependency.
    - current_user (ContactModel): The authenticated user.

    Returns:
    - Contact: The created contact.
    """
    db_contact = Contact(**contact.dict(exclude_unset=True), owner_id=current_user.id)
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact

@app.get("/contacts/", response_model=List[ContactSchema])
def get_contacts(db: Session = Depends(get_db)):
    """
    Retrieves all contacts from the database.

    Parameters:
    - db (Session): Database session dependency.

    Returns:
    - List[ContactSchema]: A list of all contacts.
    """
    return db.query(Contact).all()

@app.get("/contacts/{contact_id}", response_model=ContactSchema)
def get_contact(contact_id: int, db: Session = Depends(get_db)):
    """
    Retrieves a specific contact by its ID.

    Parameters:
    - contact_id (int): The ID of the contact.
    - db (Session): Database session dependency.

    Returns:
    - ContactSchema: The retrieved contact.
    """
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact

@app.put("/contacts/{contact_id}", response_model=ContactSchema)
def update_contact(contact_id: int, contact: ContactUpdate, db: Session = Depends(get_db)):
    """
    Updates an existing contact by its ID.

    Parameters:
    - contact_id (int): The ID of the contact to update.
    - contact (ContactUpdate): The updated contact data.
    - db (Session): Database session dependency.

    Returns:
    - ContactSchema: The updated contact.
    """
    db_contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if db_contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    for key, value in contact.dict(exclude_unset=True).items():
        setattr(db_contact, key, value)
    
    db.commit()
    db.refresh(db_contact)
    return db_contact

@app.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    """
    Deletes a specific contact by its ID.

    Parameters:
    - contact_id (int): The ID of the contact to delete.
    - db (Session): Database session dependency.

    Returns:
    - dict: Success message.
    """
    db_contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if db_contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    db.delete(db_contact)
    db.commit()
    return {"ok": True}

@app.put("/users/avatar/")
def update_avatar(file: UploadFile, db: Session = Depends(get_db), current_user: ContactModel = Depends(get_current_user)):
    """
    Updates the current authenticated user's avatar.

    Parameters:
    - file (UploadFile): The uploaded avatar image.
    - db (Session): Database session dependency.
    - current_user (ContactModel): The authenticated user.

    Returns:
    - dict: Success message and the avatar URL.
    """
    result = cloudinary.uploader.upload(file.file, folder="avatars")
    current_user.avatar_url = result["url"]
    db.commit()
    return {"msg": "Avatar updated", "avatar_url": current_user.avatar_url}