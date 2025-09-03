import os
from dotenv import load_dotenv

load_dotenv()

is_dev = os.environ.get("ENV") == "dev"
is_scheduler = os.environ.get("ENV") == "scheduler"

default_query_limit = 20

# 15 days
max_trial_days = 15

image_note_prefix = "<IMAGE-NOTE:> "
doc_note_prefix = "<DOC-NOTE:> "