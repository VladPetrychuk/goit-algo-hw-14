import unittest
from sqlalchemy.orm import Session
from models import Contact, User
from utils import hash_password
from database import get_db

class TestContactModel(unittest.TestCase):

    def setUp(self):
        self.db = next(get_db())
        self.user = User(email="test@example.com", hashed_password=hash_password("password"))
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.query(Contact).delete()
        self.db.query(User).delete()
        self.db.commit()

    def test_create_contact(self):
        contact = Contact(
            first_name="John",
            last_name="Doe",
            email="johndoe@example.com",
            phone="123456789",
            birthday="1990-01-01",
            owner_id=self.user.id
        )
        self.db.add(contact)
        self.db.commit()

        saved_contact = self.db.query(Contact).filter_by(email="johndoe@example.com").first()
        self.assertIsNotNone(saved_contact)
        self.assertEqual(saved_contact.first_name, "John")

if __name__ == '__main__':
    unittest.main()