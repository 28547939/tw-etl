import subprocess
import asyncio

# TODO: FastAPI
import aiohttp
from aiohttp import web

import argparse
import logging
import yaml, json
import random
import traceback 

import datetime

import os
import re

from dataclasses import dataclass

from typing import Dict, Optional

from stream_manager import state

from stream_manager.common import stream_state, stream_config, json_encoder
from stream_manager.state import state


class actual_defaultdict(dict):
    def __init__(self, **defaults):
        self._defaults=defaults
    def __missing__(self, key):
        return self._defaults.get(key)

class manager():

    def __init__(self, config_path, logger):
        self._config_path=config_path
        self._logger=logger

        self.stream_config={}
        self.ext_streamlist=[]
        self.awaitables=[]
        self.stream_lock : Dict[str, asyncio.Lock]={}
        self.stream_state : Dict[str, stream_state]={}

        self.load_config()

        self.state=state(
            **{
                k: self.config[k] for k in
                filter(lambda k: k in ['state_path', 'state_url', 'state_url_timeout_sec'], self.config.keys())
            }
        )


    async def start(self):

        try:
            self.stream_state=await self.state.load()
        except Exception as e:
            self._logger.error(f'could not load state: {e}')
            return

        if self.stream_state is None:
            self._logger.warning('note: state.load() returned None, reinitializing state')
            self.stream_state=dict()

        # resume existing state
        for k, state in self.stream_state.items():
            if not k in self.stream_config:
                self._logger.error(f'could not resume stream {k}: not configured')
                continue

            state.resumed=True
            self.awaitables.append(asyncio.create_task(self.try_stream(self.stream_config[k], state.poll_attempt)))
        

        await self.start_http_server()

        if self.config['poll'] == True:
            await self.spawn_poll_tasks(self.config['poll_interval'])

        # wait for all tasks to complete, including any newly arrived ones
        while len(self.awaitables) > 0:
            awaitable=self.awaitables.pop()
            try:
                await awaitable
            except Exception as e:
                self._logger.error(f'awaitable list: exception: {e}')
                print(traceback.format_exc())


    def load_config(self):
        self.config=actual_defaultdict(
            poll=True,
            poll_interval=240,
            retry_count=50,
        )

        with open(self._config_path, 'rb') as f:
            self.config.update(yaml.safe_load(f))
                               
    
        self._listen_addr = self.config['listen_addr']
        self._listen_port = self.config['listen_port']

        self.stream_config={}
        self.ext_streamlist=[]

        k=list(self.stream_lock.keys())
        for s_id in k:
            if s_id not in self.stream_state:
                del self.stream_lock[s_id]
            

        def add_stream(s_config):
            self.stream_config[s_config.stream_id]=s_config
            self.stream_lock[s_id]=asyncio.Lock()

            self._logger.debug(f'load_config: added stream {s_config}')

        # generate stream config 
        for fmt, data in self.config['streams'].items():
            for s_id in data['streams']:
                s_config=stream_config(
                    stream_id=s_id,
                    qid=fmt,
                    qlist=data['format'],
                    retries=self.config['retry_count']
                )
                add_stream(s_config)

        ext_streamlist_dir=self.config['ext_streamlist_dir']
        for filename in os.listdir(ext_streamlist_dir):
            path=os.path.join(ext_streamlist_dir, filename)
            with open(path, 'rb') as f:
                ext_streamlist=json.load(f)

                for s_id in ext_streamlist:
                    s_id=s_id.replace('#', '')

                    if s_id in self.ext_streamlist:
                        continue

                    if len(s_id) == 0 or s_id.isspace():
                        continue

                    self.ext_streamlist.append(s_id)
                    if s_id not in self.stream_config:
                        s_config=stream_config(
                            stream_id=s_id,
                            qid='audio_only',
                            qlist='audio_only',
                            retries=self.config['retry_count']
                        )

                        add_stream(s_config)

        #print(self.config)
        self._logger.info('successfully loaded config and ext-streamlist')
        
    async def online_handler(self, request, match):
        try:
            stream=match['stream']
        except KeyError:
            self._logger.error('online_handler: no stream provided')
            # TODO dump request

        self._logger.debug(f'online_handler: {stream}')
        if stream in self.stream_config:
            self.awaitables.append(asyncio.create_task(self.try_stream(self.stream_config[stream], False)))
        else:
            self._logger.info(f'online_handler({stream}): not configured, ignoring')

        return {}

    async def offline_handler(self, request, match):
        try:
            s_id=match['stream']
        except KeyError:
            self._logger.error('offline_handler: no stream provided')

        # TODO stop retries
        return {}

    async def kill_handler(self, request, match):
        try:
            s_id=match['stream']
        except KeyError:
            self._logger.error('kill_handler: no stream provided')

        # TODO kill process
        return {}

    async def state_handler(self, request, match):
        self._logger.info(f'state_handler')
        return self.stream_state


    async def write_state(self):
        await self.state.write(self.stream_state, state_path=self.config['state_path'], state_url=self.config['state_url'])


    async def start_http_server(self):

        async def reload_handler(request, match):
            self.load_config()
            return {}

        async def ext_streamlist_handler(request, match):
            return self.ext_streamlist


        router=aiohttp.web.UrlDispatcher()
        router.add_routes([
            web.post('/online/{stream}', self.online_handler),
            #web.post('/offline/{stream}', self.online_handler), TODO
            #web.post('/kill/{stream}', self.online_handler), TODO
            web.get('/state', self.state_handler),
            web.get('/ext-streamlist', ext_streamlist_handler),
            web.post('/reload', reload_handler),
        ])

        def to_json(data):
            return json.dumps(data, indent=4, cls=json_encoder)+"\n"

        async def handler(request):
            match=await router.resolve(request)
            if match.http_exception:
                return aiohttp.web.Response(text='', status=match.http_exception.status)
            
            try:
                ret=await match.handler(request, match)
            except Exception as e:
                print(traceback.format_exc())
                return aiohttp.web.Response(text=to_json({
                    'error': str(e),
                }), status=500)

            return aiohttp.web.Response(text=to_json(ret), status=200)


        server = web.Server(handler)
        runner = web.ServerRunner(server)
        await runner.setup()
        x = web.TCPSite(runner, str(self._listen_addr), self._listen_port)
        await x.start()

    """
    TODO
    Detect a streamlink (shell script) instance which has stalled in some way.
    Specifically: kill the process if there have not been any recent data, AND no
    recent retries. 
    
    normally, when there isn't any recent data (file modification is not recent), 
    streamlink will fail and exit, which is our signal to invoke a retry.
    if this doesn't happen, we need to kill the "stale" process manually
    """
    async def stream_healthcheck_task(self, s_id):
        while True:
            if s_id not in self.stream_config:
                break

            await asyncio.sleep(60)
        
            
        

    def video_path(self, directory, s_config, state, retry_id):
        video_filename=f'{s_config.stream_id}_{s_config.qid}_{state.datestr}_{retry_id}.mkv'
        video_path=os.path.join(directory, video_filename)
        return video_path

    """
    poll_attempt (formerly "retry_if_empty"): if False, we will process retries even if there was no file created
        or that file is empty after the dowload process exits
        poll_attempt should be False only when we have a definitive "online" signal, e.g. from Chatty
        this allows us to poll without retries
    """
    async def try_stream(self, s_config, poll_attempt):
        s_id=s_config.stream_id.lower()

        retry_id=0


        if s_id in self.stream_state and self.stream_state[s_id].poll_attempt == False and self.stream_lock[s_id].locked():
            self._logger.info(f'try_stream({s_id}): already online, abandoning attempt')
            return

        # prevent multiple simultaneous download attempts
        await self.stream_lock[s_id].acquire()


        if s_id not in self.stream_state:
            datestr=datetime.datetime.now().isoformat()
            log_filename=f'{s_config.stream_id}_{s_config.qid}_{datestr}'
            log_path=os.path.join(self.config['download_log_dir'], log_filename)

            self.stream_state[s_id]=stream_state(
                pid=None,
                retry_id=retry_id,
                config=s_config,
                log_path=log_path,
                datestr=datestr,
                poll_attempt=poll_attempt,
                resumed=False,
            )
            await self.write_state()

        retry_id=self.stream_state[s_id].retry_id
        state=self.stream_state[s_id]

        try:
            while retry_id <= s_config.retries:
                self._logger.info(f'try_stream({s_id}): attempting download (retry_id={retry_id})')

                video_path_thistry=self.video_path(self.config['download_dir'], s_config, state, retry_id)

                state.retry_id=retry_id
                await self.write_state()

                if state.pid is None:
                    args=[
                        s_config.stream_id,
                        s_config.qlist,
                        video_path_thistry,
                        state.log_path,
                    ]

                    if 'streamlink_args' in self.config and s_id in self.config['streamlink_args']:
                        extra_args=self.config['streamlink_args'][s_id]
                        args.append(extra_args)
                        self._logger.info(f'try_stream({s_id}): extra arguments for streamlink: {extra_args}')
                    else:
                        args.append('')

                    # TODO need a debug mode where stdout, stderr are visible
                    proc_obj=await asyncio.create_subprocess_exec(
                        self.config['download_script'],
                        *args,
                        stdout=subprocess.DEVNULL,  
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )

                    self.stream_state[s_id].pid=proc_obj.pid
                    await self.write_state()

                    await proc_obj.wait()
                else:
                    # poll the process
                    self._logger.debug(f'try_stream({s_id}): polling on existing process {state.pid}')
                    while True:
                        try:
                            os.kill(state.pid, 0)
                        except:
                            self._logger.debug(f'try_stream({s_id}): existing process {state.pid} exited, continuing retries')
                            break
                        await asyncio.sleep(1)


                self._logger.debug(f'try_stream({s_id}): process {state.pid} exited, removing PID')
                self.stream_state[s_id].pid=None
                await self.write_state()

                # check for file
                try: 
                    st=os.stat(video_path_thistry)
                    if st.st_size == 0:
                        empty=True
                    else:
                        empty=False
                    
                except FileNotFoundError: 
                    empty=True

                if empty:
                    self._logger.warning(f'try_stream({s_id}): file is empty or does not exist (retry_id={retry_id})')
                    if not poll_attempt:
                        retry_id += 1
                        continue
                    else:
                        break
                else:
                    retry_id += 1
        except Exception as e:
            self._logger.error(f'try_stream({s_id}): exception: {e}')
            print(traceback.format_exc())
            raise e
        except KeyboardInterrupt:
            exit(0)
        finally: 
            # all retries have been exhausted, or there was an exception

            try: 
                # if true, all retries have been exhausted, so we are done
                if retry_id == s_config.retries + 1:
                    # this should never happen
                    if state.pid is not None:
                        try:
                            pid=state.pid
                            os.kill(pid)
                            self._logger.debug(f'try_stream({s_id}): killed {pid}')
                        except Exception as e:
                            self._logger.warning(f'try_stream({s_id}): unable to kill {pid}: {e}')

                    del self.stream_state[s_id]
                    await self.write_state()

                    # don't bother keeping track of which retries were successful (generated data on disk) or not; 
                    # try moving all of them
                    for i in range(0, retry_id):
                        download_path=self.video_path(self.config['download_dir'], s_config, state, i)
                        completed_path=self.video_path(self.config['completed_dir'], s_config, state, i)
                        failed=[]
                        try:
                            os.rename(download_path, completed_path)
                            self._logger.debug(f'try_stream({s_id}): moved {download_path} -> {completed_path}')
                        except OSError as e:
                            failed.append((i, e))

                        # if not a single move was successful, something is wrong
                        # (we went through all s_config.retries # of retries, meaning an "online" signal was generated,
                        # but not a single file was written to disk)
                        if len(failed) == retry_id + 1:
                            self._logger.error(f'try_stream: could not move to completed: {failed}')
                else:
                    # it was just a failed poll attempt (normal)
                    if state.poll_attempt == True:
                        del self.stream_state[s_id]
                        await self.write_state()
                    else:
                        # all retries should be attempted unless it's a poll attempt
                        # this indicates an exception occurred earlier (in the outermost try)
                        self._logger.warning(f'try_stream({s_id}): exited from loop without completing all retries')
            except Exception as e:
                self._logger.warning(f'try_stream({s_id}): finally threw exception: {e}')
            # 'finally' finally, executed no matter what
            finally:
                self.stream_lock[s_id].release()



    async def poll_task(self, s_config, interval):
        def jitter(interval):
            return random.randint(0, interval)

        blocklist=self.config['blocklist']
        if s_config.stream_id in blocklist:
            self._logger.warning(f'poll_task: stream {s_config.stream_id} in blocklist, skipping')
            return

        await asyncio.sleep(jitter(interval))
        while True:
            self._logger.info(f'poll_task: trying {s_config.stream_id}')
            await self.try_stream(s_config, True)
            await asyncio.sleep(interval)

    async def spawn_poll_tasks(self, interval):
        for s_id, s_config in self.stream_config.items():
            self.awaitables.append(asyncio.create_task(self.poll_task(s_config, interval)))
