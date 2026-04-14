import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(".env")
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

def clear_tables():
    print("Clearing case_results from Supabase...")
    # Cannot truncate directly from client usually without RPC, but can do delete with multiple filters
    # Let's fetch all IDs and delete them or delete where id is not null.
    try:
        # Some versions allow generic filters like "eq" on something that's always true but Supabase JS/PY doesn't have delete all directly
        # Let's just fetch all ids and delete.
        res = sb.table("case_results").select("id").execute()
        ids = [row["id"] for row in res.data]
        if ids:
            print(f"Deleting {len(ids)} case_results...")
            for i in range(0, len(ids), 100):
                batch_ids = ids[i:i+100]
                sb.table("case_results").delete().in_("id", batch_ids).execute()
        print("Done!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    clear_tables()
