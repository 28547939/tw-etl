import json
import httpx
import logging

from stream_manager.common import json_encoder, stream_state, stream_config

"""
handle reading/writing state for the manager, with the following rules/assumptions:
- always default to loading from HTTP if the state_url we're initalized with is not None
- if HTTP is not available or not specified, load from local file
- always write state to both HTTP (if specified during initialization) and file
"""
class state():

    def __init__(self, state_path, state_url=None, http_timeout=5) -> None:
        self.state_path=state_path
        self.state_url=state_url
        self.http_timeout=http_timeout
        self.logger=logging.getLogger('stream_manager')

    """
    write the state to the local file and to the HTTP server
    TODO: for HTTP, use a FIFO queue and cancel any waiting (but not in-process) writes when a new write arrives
    """
    async def write(self, stream_state, state_path, state_url=None):
        state_json=json.dumps(stream_state, cls=json_encoder)
        with open(state_path, 'w', encoding='utf-8') as f:
            f.write(state_json)

        try: 
            if self.state_url is not None:
                # TODO - re-use client object
                async with httpx.AsyncClient() as client:
                    r=await client.put(self.state_url, data=state_json, timeout=self.http_timeout)
                    r.raise_for_status()
                    return True
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            self.logger.error(f'state.write failed over HTTP: {e}')

    def _load_data(self, struct):
        try:
            state={}
            for k, s_state in struct.items():

                s_config=stream_config(**(s_state['config']))
                del s_state['config']

                state[k]=stream_state(
                    **s_state,
                    config=s_config
                )

            return state

        except KeyError as e:
            self._logger.warning(f'_load_data failed: {str(e)}') # TODO
            return None

    async def load(self):

        try: 
            if self.state_url is not None:
                async with httpx.AsyncClient() as client:
                    r=await client.get(self.state_url, timeout=self.http_timeout)
                    r.raise_for_status()
                    return self._load_data(r.json())
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            self.logger.error(f'state.load failed over HTTP: {e}')


        # if we did not return above, fall back to reading from local file
        try:
            with open(self.state_path, 'r', encoding='utf-8') as f:
                try:
                    struct=json.load(f)
                    return self._load_data(struct)
                except json.JSONDecodeError as e:
                    self.logger.error(f'state.load failed from file: {e}')

        except FileNotFoundError:
            return None

