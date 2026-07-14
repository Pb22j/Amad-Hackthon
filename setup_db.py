import pandas as pd
from sqlalchemy import create_engine


file1 = 'fake_users_1000 (1).csv'
file2 = 'nafi_1000_fake_users_advanced.csv'


DATABASE_URL = "sqlite:///nafi.db"

try:
    engine = create_engine(DATABASE_URL)
    
    print("Uploading first file (basic_users)...")
    df1 = pd.read_csv(file1)
    df1.to_sql('basic_users', engine, if_exists='replace', index=False)
    print("First file uploaded successfully!")

    print("Uploading second file (advanced_users)...")
    df2 = pd.read_csv(file2)
    df2.to_sql('advanced_users', engine, if_exists='replace', index=False)
    print("Second file uploaded successfully!")

    print("Success! SQLite Database 'nafi.db' is ready with both tables. 🚀")

except Exception as e:
    print("Error occurred during upload:")
    print(e)