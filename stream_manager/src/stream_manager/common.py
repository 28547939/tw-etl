from dataclasses import dataclass
import json

from typing import Optional

class json_encoder(json.JSONEncoder):
    def default(self, x):
        return x.__dict__


# config for a stream
@dataclass()
class stream_config():
    stream_id: str
    qid: str
    qlist: str
    retries: int

# state for a specific stream
@dataclass()
class stream_state():
    pid : Optional[int]

    # current retry ID, starting from 0 (first try)
    retry_id : int

    # config this stream is currently using - could theoretically change
    # mid-stream
    config : stream_config

    datestr : str
    log_path : str

    poll_attempt: bool
    resumed : bool
