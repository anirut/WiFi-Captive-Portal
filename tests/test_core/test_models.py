from app.core.models import Guest, Session, Voucher, Room, Policy, PMSAdapter, AdminUser

def test_models_importable():
    assert Guest.__tablename__ == "guests"
    assert Session.__tablename__ == "sessions"
    assert Voucher.__tablename__ == "vouchers"
    assert Room.__tablename__ == "rooms"
    assert Policy.__tablename__ == "policies"
    assert PMSAdapter.__tablename__ == "pms_adapters"
    assert AdminUser.__tablename__ == "admin_users"
