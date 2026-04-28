import sys
import os
import sqlite3

# Добавляем корень проекта в путь
sys.path.append(os.getcwd())

def test_db():
    print("Testing database...")
    from src.database.models import init_db, check_and_fix_db, get_db_connection
    init_db()
    check_and_fix_db()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        required_tables = ['users', 'products', 'orders', 'cart', 'favorites', 'admins', 'promo_codes']
        
        for rt in required_tables:
            if rt in table_names:
                print(f"✅ Table {rt} exists")
            else:
                print(f"❌ Table {rt} MISSING")
                return False
    return True

def test_imports():
    print("\nTesting imports...")
    try:
        from src.handlers import user_handlers
        from src.handlers import admin_handlers
        from src.keyboards import builders
        from src.states import states
        print("✅ All imports successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_config():
    print("\nTesting config...")
    from src.config import BOT_TOKEN
    if BOT_TOKEN == "YOUUR_BOT_TOKEN":
        print("⚠️ Warning: Default BOT_TOKEN is still in use")
    else:
        print("✅ BOT_TOKEN is set")
    return True

if __name__ == "__main__":
    success = True
    if not test_db(): success = False
    if not test_imports(): success = False
    if not test_config(): success = False
    
    if success:
        print("\n🎉 All checks passed! The bot is ready to be launched.")
    else:
        print("\n🚨 Some checks failed. Please review the output.")
        sys.exit(1)
